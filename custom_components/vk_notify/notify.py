"""
VK Notify (Keyboard Edition) v1.0.4fix
Bulletproof response parsing for messages.send
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

VK_API_SEND = "https://api.vk.com/method/messages.send"
VK_API_EDIT = "https://api.vk.com/method/messages.edit"
VK_API_DELETE = "https://api.vk.com/method/messages.delete"
VK_API_WALL = "https://api.vk.com/method/wall.post"
VK_API_ACTIVITY = "https://api.vk.com/method/messages.setActivity"
VK_API_REACTION = "https://api.vk.com/method/messages.sendReaction"
VK_API_PIN = "https://api.vk.com/method/messages.pin"
VK_API_USERS_GET = "https://api.vk.com/method/users.get"
VK_API_MESSAGES_EDIT_CHAT = "https://api.vk.com/method/messages.editChat"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([VkNotifyEntity(hass, entry)])
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service("send_message", {vol.Required("message"): cv.string, vol.Optional("title"): cv.string, vol.Optional("keyboard"): dict, vol.Optional("template"): dict, vol.Optional("lat"): cv.string, vol.Optional("long"): cv.string, vol.Optional("reply_to"): cv.positive_int}, "async_send_message", supports_response=SupportsResponse.OPTIONAL)
    platform.async_register_entity_service("send_photo", {vol.Optional("url"): cv.string, vol.Optional("file"): cv.string, vol.Optional("message"): cv.string, vol.Optional("keyboard"): dict, vol.Optional("reply_to"): cv.positive_int}, "async_send_photo", supports_response=SupportsResponse.OPTIONAL)
    platform.async_register_entity_service("send_file", {vol.Required("file"): cv.string, vol.Optional("message"): cv.string, vol.Optional("keyboard"): dict, vol.Optional("reply_to"): cv.positive_int}, "async_send_file", supports_response=SupportsResponse.OPTIONAL)
    platform.async_register_entity_service("wall_post", {vol.Optional("message"): cv.string, vol.Optional("file"): cv.string}, "async_wall_post", supports_response=SupportsResponse.OPTIONAL)
    platform.async_register_entity_service("edit_message", {vol.Required("message"): cv.string, vol.Optional("message_id"): cv.positive_int, vol.Optional("conversation_message_id"): cv.positive_int, vol.Optional("keyboard"): dict}, "async_edit_message")
    platform.async_register_entity_service("delete_message", {vol.Optional("message_id"): cv.positive_int, vol.Optional("conversation_message_id"): cv.positive_int}, "async_delete_message")
    platform.async_register_entity_service("set_activity", {vol.Required("type"): vol.In(["typing", "audiomsg"])}, "async_set_activity")
    platform.async_register_entity_service("send_reaction", {vol.Required("conversation_message_id"): cv.positive_int, vol.Required("reaction_id"): cv.positive_int}, "async_send_reaction")
    platform.async_register_entity_service("pin_message", {vol.Optional("message_id"): cv.positive_int, vol.Optional("conversation_message_id"): cv.positive_int}, "async_pin_message")
    platform.async_register_entity_service("send_voice", {vol.Required("file"): cv.string, vol.Optional("message"): cv.string}, "async_send_voice", supports_response=SupportsResponse.OPTIONAL)
    platform.async_register_entity_service("send_sticker", {vol.Required("sticker_id"): cv.positive_int, vol.Optional("reply_to"): cv.positive_int}, "async_send_sticker", supports_response=SupportsResponse.OPTIONAL)
    platform.async_register_entity_service("edit_chat", {vol.Required("title"): cv.string}, "async_edit_chat")
    platform.async_register_entity_service("get_user_info", {vol.Required("user_id"): vol.Any(cv.positive_int, cv.string)}, "async_get_user_info", supports_response=SupportsResponse.ONLY)

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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"peer_id": self._peer_id, "last_message_id": self._last_message_id, "last_cmid": self._last_cmid}

    async def _internal_send(self, endpoint: str, params: dict) -> ServiceResponse:
        session = async_get_clientsession(self.hass)
        params["access_token"] = self._access_token
        params["v"] = VK_API_VERSION
        if endpoint == VK_API_SEND:
            params["peer_id"] = self._peer_id
            params["random_id"] = random.randint(0, 2**31)

        try:
            async with session.post(endpoint, data=params) as resp:
                res = await resp.json()
                if "error" in res: raise HomeAssistantError(f"VK API Error: {res['error']}")
                if endpoint == VK_API_SEND and "response" in res:
                    msg_info = res["response"]
                    
                    # --- ПУЛЕНЕПРОБИВАЕМАЯ ПРОВЕРКА ОТВЕТА ВК ---
                    if isinstance(msg_info, list) and len(msg_info) > 0:
                        msg_info = msg_info[0] 
                    
                    if isinstance(msg_info, int):
                        self._last_message_id = msg_info
                        self._last_cmid = None
                    elif isinstance(msg_info, dict):
                        self._last_message_id = msg_info.get("message_id") or msg_info.get("id")
                        self._last_cmid = msg_info.get("conversation_message_id")
                        
                    # ==============================================================
                    # ИСПРАВЛЕНИЕ: Запрашиваем conversation_message_id у ВК API
                    # ==============================================================
                    if self._last_message_id and not self._last_cmid:
                        try:
                            get_params = {
                                "access_token": self._access_token,
                                "v": VK_API_VERSION,
                                "message_ids": self._last_message_id
                            }
                            async with session.post("https://api.vk.com/method/messages.getById", data=get_params) as get_resp:
                                get_res = await get_resp.json()
                                if "response" in get_res and get_res["response"].get("items"):
                                    self._last_cmid = get_res["response"]["items"][0].get("conversation_message_id")
                        except Exception as e:
                            pass # Игнорируем ошибку, чтобы не сломать саму отправку
                    # ==============================================================
                        
                    self.async_write_ha_state()
                    return {"message_id": self._last_message_id, "conversation_message_id": self._last_cmid}
                return res.get("response")
        except Exception as e: raise HomeAssistantError(f"Connection Error: {e}")

    def _prepare_reply(self, params: dict, reply_to: int | None) -> None:
        if not reply_to: return
        if self._peer_id >= 2000000000:
            params["forward"] = json.dumps({
                "peer_id": self._peer_id,
                "conversation_message_ids": [reply_to],
                "is_reply": 1
            }, ensure_ascii=False)
        else:
            params["reply_to"] = reply_to

    async def async_send_message(self, message: str, title: str | None = None, **kwargs) -> ServiceResponse:
        if title: message = f"{title}\n{message}"
        params = {"message": message}
        if "keyboard" in kwargs: params["keyboard"] = json.dumps(kwargs["keyboard"], ensure_ascii=False)
        if "template" in kwargs: params["template"] = json.dumps(kwargs["template"], ensure_ascii=False)
        if "lat" in kwargs and "long" in kwargs:
            params["lat"], params["long"] = kwargs["lat"], kwargs["long"]
        self._prepare_reply(params, kwargs.get("reply_to"))
        return await self._internal_send(VK_API_SEND, params)

    async def async_send_photo(self, **kwargs) -> ServiceResponse:
        path = kwargs.get("url") or kwargs.get("file")
        params = {"message": kwargs.get("message", "")}
        if path: params["attachment"] = await async_upload_file(self.hass, self._access_token, self._peer_id, path)
        if kwargs.get("keyboard"): params["keyboard"] = json.dumps(kwargs["keyboard"], ensure_ascii=False)
        self._prepare_reply(params, kwargs.get("reply_to"))
        return await self._internal_send(VK_API_SEND, params)

    async def async_send_file(self, **kwargs) -> ServiceResponse:
        params = {"message": kwargs.get("message", ""), "attachment": await async_upload_file(self.hass, self._access_token, self._peer_id, kwargs["file"])}
        if kwargs.get("keyboard"): params["keyboard"] = json.dumps(kwargs["keyboard"], ensure_ascii=False)
        self._prepare_reply(params, kwargs.get("reply_to"))
        return await self._internal_send(VK_API_SEND, params)

    async def async_wall_post(self, **kwargs) -> ServiceResponse:
        params = {"owner_id": f"-{self.hass.data['vk_notify'][self._entry.entry_id]['data']['group_id']}", "message": kwargs.get("message", "")}
        if kwargs.get("file"): params["attachments"] = await async_upload_file(self.hass, self._access_token, self._peer_id, kwargs["file"])
        return await self._internal_send(VK_API_WALL, params)

    async def async_edit_message(self, message: str, **kwargs) -> None:
        params = {"peer_id": self._peer_id, "message": message}
        if kwargs.get("message_id"): params["message_id"] = kwargs["message_id"]
        elif kwargs.get("conversation_message_id"): params["conversation_message_id"] = kwargs["conversation_message_id"]
        if "keyboard" in kwargs: params["keyboard"] = json.dumps(kwargs["keyboard"], ensure_ascii=False)
        await self._internal_send(VK_API_EDIT, params)

    async def async_delete_message(self, **kwargs) -> None:
        params = {"peer_id": self._peer_id, "delete_for_all": 1}
        if kwargs.get("message_id"): params["message_ids"] = kwargs["message_id"]
        if kwargs.get("conversation_message_id"): params["cmids"] = kwargs["conversation_message_id"]
        await self._internal_send(VK_API_DELETE, params)

    async def async_set_activity(self, type: str, **kwargs) -> None:
        await self._internal_send(VK_API_ACTIVITY, {"peer_id": self._peer_id, "type": type})

    async def async_send_reaction(self, conversation_message_id: int, reaction_id: int, **kwargs) -> None:
        await self._internal_send(VK_API_REACTION, {"peer_id": self._peer_id, "cmid": conversation_message_id, "reaction_id": reaction_id})

    async def async_pin_message(self, **kwargs) -> None:
        params = {"peer_id": self._peer_id}
        if kwargs.get("message_id"): params["message_id"] = kwargs["message_id"]
        elif kwargs.get("conversation_message_id"): params["conversation_message_id"] = kwargs["conversation_message_id"]
        await self._internal_send(VK_API_PIN, params)

    async def async_send_voice(self, **kwargs) -> ServiceResponse:
        params = {"attachment": await async_upload_file(self.hass, self._access_token, self._peer_id, kwargs["file"]), "message": kwargs.get("message", "")}
        return await self._internal_send(VK_API_SEND, params)

    async def async_send_sticker(self, sticker_id: int, **kwargs) -> ServiceResponse:
        params = {"sticker_id": sticker_id}
        self._prepare_reply(params, kwargs.get("reply_to"))
        return await self._internal_send(VK_API_SEND, params)

    async def async_edit_chat(self, title: str, **kwargs) -> None:
        if self._peer_id < 2000000000: raise HomeAssistantError("edit_chat only for groups")
        await self._internal_send(VK_API_MESSAGES_EDIT_CHAT, {"chat_id": self._peer_id - 2000000000, "title": title})

    async def async_get_user_info(self, user_id: int | str, **kwargs) -> ServiceResponse:
        uid_str = str(user_id).replace("[VK ID: ", "").replace("]", "").strip()
        uid_int = int(uid_str) if uid_str.lstrip('-').isdigit() else 0
        if not uid_int or uid_int >= 2000000000: return {"full_name": "Система", "is_online": False}
        session = async_get_clientsession(self.hass)
        try:
            async with session.post(VK_API_USERS_GET, data={"user_ids": str(uid_int), "fields": "online,last_seen", "lang": "ru", "v": VK_API_VERSION, "access_token": self._access_token}) as resp:
                res = await resp.json()
                if "response" in res and res["response"]:
                    u = res["response"][0]
                    return {
                        "full_name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip(),
                        "is_online": bool(u.get("online", 0)),
                        "last_seen": u.get("last_seen", {}).get("time", 0)
                    }
        except Exception: pass
        return {"full_name": "Неизвестно", "is_online": False, "last_seen": 0}
