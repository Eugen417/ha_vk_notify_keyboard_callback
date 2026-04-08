from __future__ import annotations

import json
import random
from typing import Any

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_platform

from .const import CONF_ACCESS_TOKEN, CONF_PEER_ID, VK_API_VERSION
# Если VK_API_URL указан жестко как messages.send, мы будем использовать прямые ссылки
VK_API_SEND = "https://api.vk.com/method/messages.send"
VK_API_EDIT = "https://api.vk.com/method/messages.edit"
VK_API_DELETE = "https://api.vk.com/method/messages.delete"

from .helpers import async_upload_file


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([VkNotifyEntity(hass, entry)])

    # Регистрируем новые службы для сущности
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        "edit_message",
        {
            vol.Required("message"): cv.string,
            vol.Optional("message_id"): cv.positive_int,
            vol.Optional("conversation_message_id"): cv.positive_int,
            vol.Optional("keyboard"): dict,
        },
        "async_edit_message",
    )

    platform.async_register_entity_service(
        "delete_message",
        {
            vol.Optional("message_id"): cv.positive_int,
            vol.Optional("conversation_message_id"): cv.positive_int,
        },
        "async_delete_message",
    )


class VkNotifyEntity(NotifyEntity):
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._access_token: str = entry.data[CONF_ACCESS_TOKEN]
        self._peer_id: int = entry.data[CONF_PEER_ID]
        self._last_message_id: int | None = None
        
        self._attr_unique_id = entry.entry_id
        
        base_name = entry.data.get("name", "VK Notify")
        self._attr_name = f"{base_name} {self._peer_id}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Добавляем атрибуты, включая ID последнего отправленного сообщения."""
        return {
            "peer_id": self._peer_id,
            "last_message_id": self._last_message_id,
        }

    async def async_send_message(self, message: str, title: str | None = None, **kwargs) -> None:
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
            if "keyboard" in data:
                params["keyboard"] = json.dumps(data["keyboard"], ensure_ascii=False)
            
            if "video" in data:
                video_path = data["video"]
                try:
                    attachment = await async_upload_file(self.hass, self._access_token, self._peer_id, video_path)
                    params["attachment"] = attachment
                except Exception as e:
                    params["message"] += f"\n\n[⚠️ Ошибка прикрепления видео: {e}]"

        try:
            async with session.post(VK_API_SEND, data=params) as resp:
                data_json = await resp.json()
        except Exception as err:
            raise HomeAssistantError(f"Failed to connect to VK API: {err}") from err

        if "error" in data_json:
            raise HomeAssistantError(f"VK API error: {data_json['error']}")

        # Запоминаем ID сообщения, чтобы его можно было удалить/изменить позже
        if "response" in data_json:
            self._last_message_id = data_json["response"]
            self.async_write_ha_state()

    async def async_edit_message(self, message: str, message_id: int = None, conversation_message_id: int = None, keyboard: dict | None = None) -> None:
        """Служба для редактирования сообщения."""
        session = async_get_clientsession(self.hass)
        params = {
            "access_token": self._access_token,
            "peer_id": self._peer_id,
            "message": message,
            "v": VK_API_VERSION,
        }
        
        if message_id:
            params["message_id"] = message_id
        elif conversation_message_id:
            params["conversation_message_id"] = conversation_message_id
        else:
            raise HomeAssistantError("Укажите message_id или conversation_message_id")

        if keyboard:
            params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)

        async with session.post(VK_API_EDIT, data=params) as resp:
            data_json = await resp.json()
            if "error" in data_json:
                raise HomeAssistantError(f"Ошибка редактирования ВК: {data_json['error']}")

    async def async_delete_message(self, message_id: int = None, conversation_message_id: int = None) -> None:
        """Служба для удаления сообщения."""
        session = async_get_clientsession(self.hass)
        params = {
            "access_token": self._access_token,
            "peer_id": self._peer_id,
            "delete_for_all": 1,
            "v": VK_API_VERSION,
        }
        
        if message_id:
            params["message_ids"] = message_id
        elif conversation_message_id:
            params["cmids"] = conversation_message_id
        else:
            raise HomeAssistantError("Укажите message_id или conversation_message_id")

        async with session.post(VK_API_DELETE, data=params) as resp:
            data_json = await resp.json()
            if "error" in data_json:
                raise HomeAssistantError(f"Ошибка удаления ВК: {data_json['error']}")
