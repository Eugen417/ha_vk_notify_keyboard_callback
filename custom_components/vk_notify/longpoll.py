from __future__ import annotations

import asyncio
import logging

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_PEER_ID, DOMAIN, VK_API_LONGPOLL_SERVER, VK_API_MARK_AS_READ, VK_API_VERSION

_LOGGER = logging.getLogger(__name__)


class VkLongPollManager:
    """Менеджер Long Poll для получения входящих сообщений сообщества VK.

    Один экземпляр создаётся на уникальный group_id и разделяется между всеми
    записями интеграции с одним токеном. Входящие сообщения публикуются как
    события HA: vk_notify_command (начинаются с /) и vk_notify_text (обычный текст).
    """

    def __init__(self, hass: HomeAssistant, access_token: str, group_id: int) -> None:
        self._hass = hass
        self._access_token = access_token
        self._group_id = group_id
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Запустить фоновую задачу Long Poll."""
        self._task = self._hass.async_create_background_task(
            self._run(), f"vk_longpoll_{self._group_id}"
        )

    async def stop(self) -> None:
        """Остановить фоновую задачу Long Poll."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _get_server(self) -> tuple[str, str, str]:
        """Получить адрес Long Poll сервера, ключ и начальный ts от VK API.

        Требует права 'manage' (Управление сообществом) в токене.
        Возвращает (server, key, ts).
        """
        session = async_get_clientsession(self._hass)
        async with session.get(
            VK_API_LONGPOLL_SERVER,
            params={
                "access_token": self._access_token,
                "group_id": self._group_id,
                "v": VK_API_VERSION,
            },
        ) as resp:
            data = await resp.json()
        if "error" in data:
            err = data["error"]
            code = err.get("error_code")
            subcode = err.get("error_subcode")
            if code == 15 or subcode == 1133:
                # Токен не имеет права manage — нужно перегенерировать с нужными разрешениями
                raise RuntimeError(
                    f"Access denied (error_code={code}, subcode={subcode}). "
                    "The community token is missing the 'manage' permission. "
                    "Re-generate the token in VK community settings with 'Community management' enabled."
                )
            raise RuntimeError(f"error_code={code}: {err.get('error_msg', data['error'])}")
        r = data["response"]
        return r["server"], r["key"], r["ts"]

    async def _run(self) -> None:
        """Основной цикл опроса Long Poll сервера."""
        try:
            server, key, ts = await self._get_server()
        except Exception as err:
            _LOGGER.error("VK Long Poll: failed to get server: %s", err)
            return

        session = async_get_clientsession(self._hass)

        while True:
            try:
                async with session.get(
                    server,
                    params={"act": "a_check", "key": key, "ts": ts, "wait": 25},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json()

                failed = data.get("failed")
                if failed == 1:
                    # Устаревший ts — обновляем и продолжаем
                    ts = data["ts"]
                    continue
                if failed in (2, 3):
                    # Истёк ключ или полная потеря данных — переподключаемся
                    server, key, ts = await self._get_server()
                    continue

                ts = data["ts"]
                for update in data.get("updates", []):
                    self._handle_update(update)

            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.warning("VK Long Poll error: %s. Reconnecting in 5s.", err)
                await asyncio.sleep(5)
                try:
                    server, key, ts = await self._get_server()
                except Exception as err2:
                    _LOGGER.error("VK Long Poll: reconnect failed: %s", err2)
                    await asyncio.sleep(30)

    def _handle_update(self, update: dict) -> None:
        """Обработать одно обновление от Long Poll.

        Публикует событие HA:
        - vk_notify_command — если текст начинается с /
        - vk_notify_text    — для обычного текста

        После публикации события отмечает сообщение прочитанным.
        """
        if update.get("type") != "message_new":
            return

        message = update.get("object", {}).get("message", {})
        text: str = message.get("text", "")
        peer_id: int = message.get("peer_id")
        message_id: int = message.get("id")

        entity_id = self._find_entity_id(peer_id)
        if entity_id is None:
            # Чат не добавлен в интеграцию — игнорируем сообщение
            return

        # Общие поля для обоих типов событий
        base = {
            "group_id": self._group_id,
            "peer_id": peer_id,
            "from_id": message.get("from_id"),
            "message_id": message_id,
            "entity_id": entity_id,
        }

        if text.startswith("/"):
            # Команда: разбиваем на имя и аргументы (/команда аргументы)
            parts = text.split(maxsplit=1)
            command = parts[0][1:]  # убираем ведущий /
            args = parts[1] if len(parts) > 1 else ""
            self._hass.bus.async_fire(
                f"{DOMAIN}_command",
                {**base, "command": command, "args": args, "text": text},
            )
        else:
            self._hass.bus.async_fire(
                f"{DOMAIN}_text",
                {**base, "text": text},
            )

        # Отмечаем сообщение прочитанным
        self._hass.async_create_task(
            self._mark_as_read(peer_id, message_id)
        )

    def _find_entity_id(self, peer_id: int) -> str | None:
        """Найти entity_id notify-сущности по peer_id.

        Перебирает все записи интеграции в hass.data и ищет ту,
        чей peer_id совпадает с полученным. Затем находит entity через реестр.
        """
        ent_reg = er.async_get(self._hass)
        for entry_id, entry_data in self._hass.data.get(DOMAIN, {}).items():
            if not isinstance(entry_data, dict) or "data" not in entry_data:
                continue
            if entry_data["data"].get(CONF_PEER_ID) == peer_id:
                entities = er.async_entries_for_config_entry(ent_reg, entry_id)
                if entities:
                    return entities[0].entity_id
        return None

    async def _mark_as_read(self, peer_id: int, message_id: int) -> None:
        """Отметить сообщение прочитанным через messages.markAsRead."""
        session = async_get_clientsession(self._hass)
        try:
            async with session.get(
                VK_API_MARK_AS_READ,
                params={
                    "access_token": self._access_token,
                    "peer_id": peer_id,
                    "start_message_id": message_id,
                    "v": VK_API_VERSION,
                },
            ) as resp:
                await resp.json()
        except Exception as err:
            _LOGGER.debug("VK Long Poll: failed to mark message as read: %s", err)
