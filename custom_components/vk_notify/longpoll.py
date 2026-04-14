"""
VK Notify (Keyboard Edition) longpoll.py v1.0.5
"""

from __future__ import annotations

import asyncio
import json
import logging

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_PEER_ID, DOMAIN, VK_API_LONGPOLL_SERVER, VK_API_MARK_AS_READ, VK_API_VERSION

_LOGGER = logging.getLogger(__name__)

class VkLongPollManager:
    def __init__(self, hass: HomeAssistant, access_token: str, group_id: int) -> None:
        self._hass = hass
        self._access_token = access_token
        self._group_id = group_id
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Запуск фоновой задачи Long Poll."""
        self._task = self._hass.async_create_background_task(
            self._run(), f"vk_longpoll_{self._group_id}"
        )

    async def stop(self) -> None:
        """Остановка фоновой задачи."""
        if self._task:
            self._task.cancel()
            try: 
                await self._task
            except asyncio.CancelledError: 
                pass
            self._task = None

    async def _get_server(self) -> tuple[str, str, str]:
        """Получение данных сервера Long Poll."""
        session = async_get_clientsession(self._hass)
        async with session.get(
            VK_API_LONGPOLL_SERVER,
            params={"access_token": self._access_token, "group_id": self._group_id, "v": VK_API_VERSION},
        ) as resp:
            data = await resp.json()
            
        if "error" in data:
            raise RuntimeError(f"VK API Error: {data['error']}")
            
        r = data["response"]
        return r["server"], r["key"], r["ts"]

    async def _run(self) -> None:
        """Основной бесконечный цикл получения событий."""
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
                    ts = data["ts"]
                    continue
                if failed in (2, 3):
                    server, key, ts = await self._get_server()
                    continue

                ts = data["ts"]
                for update in data.get("updates", []):
                    self._handle_update(update)

            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                # Обычный таймаут HTTP (ничего не произошло за 25 сек), просто продолжаем цикл
                continue
            except Exception as err:
                _LOGGER.warning("VK Long Poll error: %s. Reconnecting in 5s...", err)
                await asyncio.sleep(5)
                try:
                    server, key, ts = await self._get_server()
                except Exception:
                    pass # Ошибка получения сервера, попробуем снова в следующем цикле

    def _handle_update(self, update: dict) -> None:
        """Распределение и обработка входящих событий от ВКонтакте."""
        upd_type = update.get("type")
        obj = update.get("object", {})

        # =======================================================
        # 1. ОБРАБОТКА ТЕКСТА (СООБЩЕНИЯ И КОМАНДЫ)
        # =======================================================
        if upd_type == "message_new":
            message = obj.get("message", {})
            text = message.get("text", "")
            peer_id = message.get("peer_id")
            from_id = message.get("from_id")
            cmid = message.get("conversation_message_id")
            
            ent_id = self._find_entity_id(peer_id)
            entity_status = ent_id or "not_configured"

            base = {
                "peer_id": peer_id, 
                "entity_id": entity_status, 
                "text": text,
                "from_id": from_id,
                "conversation_message_id": cmid
            }
            
            # Проверяем, является ли текст командой (начинается со слэша /)
            if text.startswith("/"):
                cmd_parts = text.split()
                command = cmd_parts[0][1:] if cmd_parts else ""
                self._hass.bus.async_fire(f"{DOMAIN}_command", {**base, "command": command})
            else:
                self._hass.bus.async_fire(f"{DOMAIN}_text", base)
            
            # Помечаем сообщение прочитанным (со стороны бота)
            self._hass.async_create_task(self._mark_as_read(peer_id, message.get("id")))

        # =======================================================
        # 2. ОБРАБОТКА НАЖАТИЙ НА INLINE CALLBACK КНОПКИ
        # =======================================================
        elif upd_type == "message_event":
            peer_id = obj.get("peer_id")
            user_id = obj.get("user_id")
            event_id = obj.get("event_id")
            payload = obj.get("payload", {})

            # VK иногда отдает payload строкой, нужно безопасно перевести в JSON
            if isinstance(payload, str):
                try: 
                    payload = json.loads(payload)
                except ValueError: 
                    pass

            ent_id = self._find_entity_id(peer_id)
            entity_status = ent_id or "not_configured"

            self._hass.bus.async_fire(
                f"{DOMAIN}_callback", 
                {
                    "payload": payload, 
                    "peer_id": peer_id, 
                    "entity_id": entity_status,
                    "user_id": user_id,
                    "conversation_message_id": obj.get("conversation_message_id")
                }
            )

            # Отправляем ответ серверу ВК, чтобы убрать "крутящийся лоадер" с кнопки
            self._hass.async_create_task(self._answer_callback(event_id, user_id, peer_id))

        # =======================================================
        # 3. СТАТУС НАБОРА ТЕКСТА ("Бот печатает...")
        # =======================================================
        elif upd_type == "message_typing_state":
            peer_id = obj.get("from_id")
            ent_id = self._find_entity_id(peer_id)
            entity_status = ent_id or "not_configured"
            
            self._hass.bus.async_fire(
                f"{DOMAIN}_typing",
                {
                    "peer_id": peer_id,
                    "entity_id": entity_status,
                    "user_id": obj.get("from_id"),
                    "state": obj.get("state", "typing")
                }
            )

        # =======================================================
        # 4. СТАТУС ПРОЧТЕНИЯ СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЕМ
        # =======================================================
        elif upd_type == "message_read":
            peer_id = obj.get("peer_id")
            ent_id = self._find_entity_id(peer_id)
            entity_status = ent_id or "not_configured"
            
            self._hass.bus.async_fire(
                f"{DOMAIN}_read",
                {
                    "peer_id": peer_id,
                    "entity_id": entity_status,
                    "user_id": obj.get("from_id", peer_id),
                    "read_message_id": obj.get("read_message_id")
                }
            )

    async def _answer_callback(self, event_id: str, user_id: int, peer_id: int) -> None:
        """Отправка ответа на callback-кнопку."""
        session = async_get_clientsession(self._hass)
        try:
            async with session.post(
                "https://api.vk.com/method/messages.sendMessageEventAnswer",
                data={
                    "access_token": self._access_token, 
                    "event_id": event_id, 
                    "user_id": user_id, 
                    "peer_id": peer_id, 
                    "v": VK_API_VERSION
                }
            ) as resp:
                await resp.json()
        except Exception as e:
            _LOGGER.debug("Failed to stop VK callback spinner: %s", e)

    def _find_entity_id(self, peer_id: int) -> str | None:
        """Поиск entity_id по peer_id в конфигурации Home Assistant."""
        ent_reg = er.async_get(self._hass)
        for entry_id, entry_data in self._hass.data.get(DOMAIN, {}).items():
            if entry_data.get("data", {}).get(CONF_PEER_ID) == peer_id:
                entities = er.async_entries_for_config_entry(ent_reg, entry_id)
                return entities[0].entity_id if entities else None
        return None

    async def _mark_as_read(self, peer_id: int, msg_id: int) -> None:
        """Пометка входящего сообщения прочитанным."""
        session = async_get_clientsession(self._hass)
        try:
            await session.get(
                VK_API_MARK_AS_READ, 
                params={
                    "access_token": self._access_token, 
                    "peer_id": peer_id, 
                    "start_message_id": msg_id, 
                    "v": VK_API_VERSION
                }
            )
        except Exception as e:
            _LOGGER.debug("Failed to mark message as read: %s", e)
