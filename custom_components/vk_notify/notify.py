from __future__ import annotations

import json
import random
from typing import Any

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_platform

from .const import CONF_ACCESS_TOKEN, CONF_PEER_ID, VK_API_VERSION
from .helpers import async_upload_file

# Эндпоинты VK API
VK_API_SEND = "https://api.vk.com/method/messages.send"
VK_API_EDIT = "https://api.vk.com/method/messages.edit"
VK_API_DELETE = "https://api.vk.com/method/messages.delete"
VK_API_WALL_POST = "https://api.vk.com/method/wall.post"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([VkNotifyEntity(hass, entry)])
    platform = entity_platform.async_get_current_platform()

    # 1. Отправить сообщение
    platform.async_register_entity_service(
        "send_message",
        {
            vol.Required("message"): cv.string,
            vol.Optional("title"): cv.string,
            vol.Optional("keyboard"): dict,
            vol.Optional("data"): dict,
        },
        "async_send_message",
        supports_response=SupportsResponse.OPTIONAL,
    )

    # 2. Редактировать сообщение
    platform.async_register_entity_service(
        "edit_message",
        {
            vol.Required("message"): cv.string,
            vol.Optional("message_id"): cv.positive_int,
            vol.Optional("conversation_message_id"): cv.positive_int,
            vol.Optional("keyboard"): dict,
            vol.Optional("attachment"): cv.string,
        },
        "async_edit_message",
    )

    # 3. Удалить сообщение
    platform.async_register_entity_service(
        "delete_message",
        {
            vol.Optional("message_id"): cv.positive_int,
            vol.Optional("conversation_message_id"): cv.positive_int,
        },
        "async_delete_message",
    )

    # 4. Отправить фото
    platform.async_register_entity_service(
        "send_photo",
        {
            vol.Optional("url"): cv.string,
            vol.Optional("file"): cv.string,
            vol.Optional("message"): cv.string,
            vol.Optional("keyboard"): dict,
        },
        "async_send_photo",
        supports_response=SupportsResponse.OPTIONAL,
    )

    # 5. Отправить файл (документ)
    platform.async_register_entity_service(
        "send_file",
        {
            vol.Required("file"): cv.string,
            vol.Optional("message"): cv.string,
            vol.Optional("keyboard"): dict,
        },
        "async_send_file",
        supports_response=SupportsResponse.OPTIONAL,
    )

    # 6. Пост на стену
    platform.async_register_entity_service(
        "wall_post",
        {
            vol.Optional("message"): cv.string,
            vol.Optional("file"): cv.string,
        },
        "async_wall_post",
        supports_response=SupportsResponse.OPTIONAL,
    )


class VkNotifyEntity(NotifyEntity):
    _attr_has_entity_name = True
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._access_token: str = entry.data[CONF_ACCESS_TOKEN]
        self._peer_id: int = entry.data[CONF_PEER_ID]
        self._last_message_id: int | None = None
        self._last_cmid: int | None = None 
        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.data.get("name", "VK Notify")
        self._attr_extra_state_attributes = {
            "peer_id": self._peer_id,
            "last_message_id": None,
            "last_cmid": None,
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "peer_id": self._peer_id,
            "last_message_id": self._last_message_id,
            "last_cmid": self._last_cmid, 
        }

    # === БАЗОВЫЙ МЕТОД ОТПРАВКИ (Используется для send_message, send_photo, send_file) ===
    async def _send_vk_message(self, message: str, attachment: str = None, keyboard: dict = None) -> ServiceResponse:
        session = async_get_clientsession(self.hass)
        params = {
            "access_token": self._access_token,
            "peer_ids": self._peer_id,
            "message": message,
            "random_id": random.randint(0, 2**31),
            "v": VK_API_VERSION,
        }

        if keyboard is not None:
            params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)
        
        if attachment:
            params["attachment"] = attachment

        try:
            async with session.post(VK_API_SEND, data=params) as resp:
                data_json = await resp.json()
                if "error" in data_json:
                    raise HomeAssistantError(f"VK Send Error: {data_json['error']}")
                
                if "response" in data_json:
                    resp_data = data_json["response"]
                    if isinstance(resp_data, list) and len(resp_data) > 0:
                        msg_info = resp_data[0]
                        self._last_message_id = msg_info.get("message_id")
                        self._last_cmid = msg_info.get("conversation_message_id")
                        self._attr_extra_state_attributes.update({
                            "last_message_id": self._last_message_id,
                            "last_cmid": self._last_cmid
                        })
                        self.async_write_ha_state()

                    return {
                        "message_id": self._last_message_id,
                        "conversation_message_id": self._last_cmid,
                        "peer_id": self._peer_id
                    }
        except Exception as err:
            raise HomeAssistantError(f"VK Connect Error: {err}")
        return None

    # === 1. ОТПРАВИТЬ СООБЩЕНИЕ ===
    async def async_send_message(self, message: str, title: str | None = None, **kwargs) -> ServiceResponse:
        if title: message = f"{title}\n{message}"
        keyboard = kwargs.get("keyboard") or (kwargs.get("data") or {}).get("keyboard")
        
        attachment = None
        data = kwargs.get("data") or {}
        if "video" in data:
            try:
                attachment = await async_upload_file(self.hass, self._access_token, self._peer_id, data["video"])
            except Exception: pass

        return await self._send_vk_message(message, attachment, keyboard)

    # === 2. РЕДАКТИРОВАТЬ СООБЩЕНИЕ ===
    async def async_edit_message(self, message: str, **kwargs) -> None:
        session = async_get_clientsession(self.hass)
        params = {"access_token": self._access_token, "peer_id": self._peer_id, "message": message, "v": VK_API_VERSION}
        
        if kwargs.get("message_id") is not None:
            params["message_id"] = kwargs["message_id"]
        elif kwargs.get("conversation_message_id") is not None:
            params["conversation_message_id"] = kwargs["conversation_message_id"]
        
        if "keyboard" in kwargs and kwargs["keyboard"] is not None:
            params["keyboard"] = json.dumps(kwargs["keyboard"], ensure_ascii=False)

        if "attachment" in kwargs and kwargs["attachment"]:
            params["attachment"] = kwargs["attachment"]

        async with session.post(VK_API_EDIT, data=params) as resp:
            data_json = await resp.json()
            if "error" in data_json: raise HomeAssistantError(f"Edit Error: {data_json['error']}")

    # === 3. УДАЛИТЬ СООБЩЕНИЕ ===
    async def async_delete_message(self, **kwargs) -> None:
        session = async_get_clientsession(self.hass)
        params = {"access_token": self._access_token, "peer_id": self._peer_id, "delete_for_all": 1, "v": VK_API_VERSION}
        
        mid = kwargs.get("message_id")
        cmid = kwargs.get("conversation_message_id")
        if not mid and not cmid: return

        if mid: params["message_ids"] = mid
        if cmid: params["cmids"] = cmid

        async with session.post(VK_API_DELETE, data=params) as resp:
            data_json = await resp.json()
            if "error" in data_json: raise HomeAssistantError(f"Delete Error: {data_json['error']}")

    # === 4. ОТПРАВИТЬ ФОТО ===
    async def async_send_photo(self, **kwargs) -> ServiceResponse:
        message = kwargs.get("message", "")
        keyboard = kwargs.get("keyboard")
        file_source = kwargs.get("url") or kwargs.get("file")
        
        attachment = None
        if file_source:
            try:
                attachment = await async_upload_file(self.hass, self._access_token, self._peer_id, file_source)
            except Exception as e:
                raise HomeAssistantError(f"Photo Upload Error: {e}")

        return await self._send_vk_message(message, attachment, keyboard)

    # === 5. ОТПРАВИТЬ ФАЙЛ ===
    async def async_send_file(self, **kwargs) -> ServiceResponse:
        message = kwargs.get("message", "")
        keyboard = kwargs.get("keyboard")
        file_source = kwargs.get("file")
        
        attachment = None
        if file_source:
            try:
                attachment = await async_upload_file(self.hass, self._access_token, self._peer_id, file_source)
            except Exception as e:
                raise HomeAssistantError(f"File Upload Error: {e}")

        return await self._send_vk_message(message, attachment, keyboard)

    # === 6. ПОСТ НА СТЕНУ ===
    async def async_wall_post(self, **kwargs) -> ServiceResponse:
        session = async_get_clientsession(self.hass)
        message = kwargs.get("message", "")
        file_source = kwargs.get("file")
        
        params = {
            "access_token": self._access_token,
            "owner_id": self._peer_id,  # Для стены используется owner_id
            "message": message,
            "v": VK_API_VERSION,
        }

        if file_source:
            try:
                attachment = await async_upload_file(self.hass, self._access_token, self._peer_id, file_source)
                params["attachments"] = attachment
            except Exception as e:
                raise HomeAssistantError(f"Wall File Upload Error: {e}")

        async with session.post(VK_API_WALL_POST, data=params) as resp:
            data_json = await resp.json()
            if "error" in data_json: 
                raise HomeAssistantError(f"Wall Post Error: {data_json['error']}")
            
            if "response" in data_json:
                return {"post_id": data_json["response"].get("post_id")}
        return None
