"""
VK Notify (Keyboard Edition) v1.0.3
Custom component for Home Assistant

Описание:
Поддерживает отправку, редактирование и удаление сообщений, посты на стену,
отправку фото, файлов, аудио, а также статусы активности, реакции и геометки.

Репозиторий: https://github.com/Eugen417/ha_vk_notify_keyboard_callback
"""
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

# Эндпоинты API VK
VK_API_SEND = "https://api.vk.com/method/messages.send"
VK_API_EDIT = "https://api.vk.com/method/messages.edit"
VK_API_DELETE = "https://api.vk.com/method/messages.delete"
VK_API_WALL = "https://api.vk.com/method/wall.post"
VK_API_ACTIVITY = "https://api.vk.com/method/messages.setActivity"
VK_API_REACTION = "https://api.vk.com/method/messages.sendReaction"
VK_API_PIN = "https://api.vk.com/method/messages.pin"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([VkNotifyEntity(hass, entry)])
    platform = entity_platform.async_get_current_platform()

    # --- СТАРЫЕ СЛУЖБЫ (Текст, Фото, Файлы, Стена, Редактирование, Удаление) ---
    platform.async_register_entity_service("send_message", {vol.Required("message"): cv.string, vol.Optional("title"): cv.string, vol.Optional("keyboard"): dict, vol.Optional("template"): dict, vol.Optional("lat"): cv.string, vol.Optional("long"): cv.string, vol.Optional("data"): dict}, "async_send_message", supports_response=SupportsResponse.OPTIONAL)
    platform.async_register_entity_service("send_photo", {vol.Optional("url"): cv.string, vol.Optional("file"): cv.string, vol.Optional("message"): cv.string, vol.Optional("keyboard"): dict}, "async_send_photo", supports_response=SupportsResponse.OPTIONAL)
    platform.async_register_entity_service("send_file", {vol.Required("file"): cv.string, vol.Optional("message"): cv.string, vol.Optional("keyboard"): dict}, "async_send_file", supports_response=SupportsResponse.OPTIONAL)
    platform.async_register_entity_service("wall_post", {vol.Optional("message"): cv.string, vol.Optional("file"): cv.string}, "async_wall_post", supports_response=SupportsResponse.OPTIONAL)
    platform.async_register_entity_service("edit_message", {vol.Required("message"): cv.string, vol.Optional("message_id"): cv.positive_int, vol.Optional("conversation_message_id"): cv.positive_int, vol.Optional("keyboard"): dict, vol.Optional("attachment"): cv.string}, "async_edit_message")
    platform.async_register_entity_service("delete_message", {vol.Optional("message_id"): cv.positive_int, vol.Optional("conversation_message_id"): cv.positive_int}, "async_delete_message")

    # --- НОВЫЕ СЛУЖБЫ (v3.0) ---
    platform.async_register_entity_service(
        "set_activity",
        {vol.Required("type"): vol.In(["typing", "audiomsg"])},
        "async_set_activity"
    )
    platform.async_register_entity_service(
        "send_reaction",
        {vol.Required("conversation_message_id"): cv.positive_int, vol.Required("reaction_id"): cv.positive_int},
        "async_send_reaction"
    )
    platform.async_register_entity_service(
        "pin_message",
        {vol.Optional("message_id"): cv.positive_int, vol.Optional("conversation_message_id"): cv.positive_int},
        "async_pin_message"
    )
    platform.async_register_entity_service(
        "send_voice",
        {vol.Required("file"): cv.string, vol.Optional("message"): cv.string},
        "async_send_voice",
        supports_response=SupportsResponse.OPTIONAL
    )


class VkNotifyEntity(NotifyEntity):
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._access_token: str = entry.data[CONF_ACCESS_TOKEN]
        self._peer_id: int = entry.data[CONF_PEER_ID]
        self._last_message_id: int | None = None
        self._last_cmid: int | None = None 
        self._attr_unique_id = entry.entry_id
        base_name = entry.data.get("name", "VK Notify")
        self._attr_name = f"{base_name} {self._peer_id}"
        self._attr_extra_state_attributes = {"peer_id": self._peer_id, "last_message_id": None, "last_cmid": None}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"peer_id": self._peer_id, "last_message_id": self._last_message_id, "last_cmid": self._last_cmid}

    async def _internal_send(self, endpoint: str, params: dict) -> ServiceResponse:
        session = async_get_clientsession(self.hass)
        params["access_token"] = self._access_token
        params["v"] = VK_API_VERSION
        if endpoint == VK_API_SEND:
            params["peer_ids"] = self._peer_id
            params["random_id"] = random.randint(0, 2**31)

        try:
            async with session.post(endpoint, data=params) as resp:
                res = await resp.json()
                if "error" in res: raise HomeAssistantError(f"VK API Error: {res['error']}")
                if endpoint == VK_API_SEND and "response" in res:
                    msg_info = res["response"][0]
                    self._last_message_id = msg_info.get("message_id")
                    self._last_cmid = msg_info.get("conversation_message_id")
                    self.async_write_ha_state()
                    return {"message_id": self._last_message_id, "conversation_message_id": self._last_cmid}
                return res.get("response")
        except Exception as e: raise HomeAssistantError(f"Connection Error: {e}")

    # --- БАЗОВЫЕ МЕТОДЫ ---
    async def async_send_message(self, message: str, title: str | None = None, **kwargs) -> ServiceResponse:
        if title: message = f"{title}\n{message}"
        params = {"message": message}
        if "keyboard" in kwargs: params["keyboard"] = json.dumps(kwargs["keyboard"], ensure_ascii=False)
        if "template" in kwargs: params["template"] = json.dumps(kwargs["template"], ensure_ascii=False)
        if "lat" in kwargs and "long" in kwargs:
            params["lat"] = kwargs["lat"]
            params["long"] = kwargs["long"]
        return await self._internal_send(VK_API_SEND, params)

    async def async_send_photo(self, **kwargs) -> ServiceResponse:
        path = kwargs.get("url") or kwargs.get("file")
        params = {"message": kwargs.get("message", "")}
        if path: params["attachment"] = await async_upload_file(self.hass, self._access_token, self._peer_id, path)
        if kwargs.get("keyboard"): params["keyboard"] = json.dumps(kwargs["keyboard"], ensure_ascii=False)
        return await self._internal_send(VK_API_SEND, params)

    async def async_send_file(self, **kwargs) -> ServiceResponse:
        params = {"message": kwargs.get("message", ""), "attachment": await async_upload_file(self.hass, self._access_token, self._peer_id, kwargs["file"])}
        if kwargs.get("keyboard"): params["keyboard"] = json.dumps(kwargs["keyboard"], ensure_ascii=False)
        return await self._internal_send(VK_API_SEND, params)

    async def async_wall_post(self, **kwargs) -> ServiceResponse:
        params = {"owner_id": self._peer_id, "message": kwargs.get("message", "")}
        if kwargs.get("file"): params["attachments"] = await async_upload_file(self.hass, self._access_token, self._peer_id, kwargs["file"])
        return await self._internal_send(VK_API_WALL, params)

    async def async_edit_message(self, message: str, **kwargs) -> None:
        params = {"peer_id": self._peer_id, "message": message}
        if kwargs.get("message_id"): params["message_id"] = kwargs["message_id"]
        elif kwargs.get("conversation_message_id"): params["conversation_message_id"] = kwargs["conversation_message_id"]
        if "keyboard" in kwargs and kwargs["keyboard"] is not None: params["keyboard"] = json.dumps(kwargs["keyboard"], ensure_ascii=False)
        if kwargs.get("attachment"): params["attachment"] = kwargs["attachment"]
        await self._internal_send(VK_API_EDIT, params)

    async def async_delete_message(self, **kwargs) -> None:
        params = {"peer_id": self._peer_id, "delete_for_all": 1}
        if kwargs.get("message_id"): params["message_ids"] = kwargs["message_id"]
        if kwargs.get("conversation_message_id"): params["cmids"] = kwargs["conversation_message_id"]
        await self._internal_send(VK_API_DELETE, params)

    # --- НОВЫЕ МЕТОДЫ (v3.0) ---
    async def async_set_activity(self, type: str, **kwargs) -> None:
        """Отправляет статус 'Печатает...' или 'Записывает аудио'."""
        params = {"peer_id": self._peer_id, "type": type}
        await self._internal_send(VK_API_ACTIVITY, params)

    async def async_send_reaction(self, conversation_message_id: int, reaction_id: int, **kwargs) -> None:
        """Ставит реакцию на конкретное сообщение."""
        params = {"peer_id": self._peer_id, "cmid": conversation_message_id, "reaction_id": reaction_id}
        await self._internal_send(VK_API_REACTION, params)

    async def async_pin_message(self, **kwargs) -> None:
        """Закрепляет сообщение в чате."""
        params = {"peer_id": self._peer_id}
        if kwargs.get("message_id"): params["message_id"] = kwargs["message_id"]
        elif kwargs.get("conversation_message_id"): params["conversation_message_id"] = kwargs["conversation_message_id"]
        await self._internal_send(VK_API_PIN, params)

    async def async_send_voice(self, **kwargs) -> ServiceResponse:
        """Отправляет голосовое сообщение (аудио)."""
        # Внимание: для идеальной работы helpers.py должен поддерживать загрузку с type='audio_message'
        # Но как базовый вариант, мы загружаем его как документ.
        params = {"message": kwargs.get("message", ""), "attachment": await async_upload_file(self.hass, self._access_token, self._peer_id, kwargs["file"])}
        return await self._internal_send(VK_API_SEND, params)
