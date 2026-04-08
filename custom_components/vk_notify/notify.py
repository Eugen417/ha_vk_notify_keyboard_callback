from __future__ import annotations

import json
import random
from typing import Any

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ACCESS_TOKEN, CONF_PEER_ID, VK_API_URL, VK_API_VERSION
from .helpers import async_upload_file


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([VkNotifyEntity(hass, entry)])


class VkNotifyEntity(NotifyEntity):
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._access_token: str = entry.data[CONF_ACCESS_TOKEN]
        self._peer_id: int = entry.data[CONF_PEER_ID]
        
        self._attr_unique_id = entry.entry_id
        
        # Формируем красивое имя: базовое название + ID чата
        base_name = entry.data.get("name", "VK Notify")
        self._attr_name = f"{base_name} {self._peer_id}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Добавляем peer_id в атрибуты, чтобы его было видно в свойствах сущности."""
        return {
            "peer_id": self._peer_id,
        }

    async def async_send_message(self, message: str, title: str | None = None, **kwargs) -> None:
        # Если передан заголовок — добавляем его первой строкой
        if title:
            message = f"{title}\n{message}"

        session = async_get_clientsession(self.hass)
        params = {
            "access_token": self._access_token,
            "peer_id": self._peer_id,
            "message": message,
            "random_id": random.randint(0, 2**31),
            "v": VK_API_VERSION,
        }

        data = kwargs.get("data")
        if data:
            # Обработка клавиатуры
            if "keyboard" in data:
                params["keyboard"] = json.dumps(data["keyboard"], ensure_ascii=False)
            
            # --- БЛОК: ЗАГРУЗКА ВИДЕО (через внешний хелпер) ---
            if "video" in data:
                video_path = data["video"]
                try:
                    # Используем готовую функцию из helpers.py
                    attachment = await async_upload_file(self.hass, self._access_token, self._peer_id, video_path)
                    params["attachment"] = attachment
                except Exception as e:
                    # Выводим ошибку в чат, если что-то пошло не так
                    params["message"] += f"\n\n[⚠️ Ошибка прикрепления видео: {e}]"
            # ---------------------------------------------------

        try:
            # Используем POST вместо GET для надежной передачи больших клавиатур и данных
            async with session.post(VK_API_URL, data=params) as resp:
                data_json = await resp.json()
        except Exception as err:
            raise HomeAssistantError(f"Failed to connect to VK API: {err}") from err

        if "error" in data_json:
            raise HomeAssistantError(f"VK API error: {data_json['error']}")
