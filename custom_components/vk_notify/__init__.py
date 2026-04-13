from __future__ import annotations

import json
import random

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, ServiceResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_GROUP_ID,
    CONF_MODE,
    CONF_PEER_ID,
    DOMAIN,
    MODE_LONGPOLL,
    VK_API_URL,
    VK_API_VERSION,
    VK_API_WALL_POST,
)
from .helpers import async_upload_file, async_upload_photo
from .longpoll import VkLongPollManager

PLATFORMS = [Platform.NOTIFY]

SERVICE_SEND_PHOTO = "send_photo"
SERVICE_SEND_FILE = "send_file"
SERVICE_WALL_POST = "wall_post"
SERVICE_SEND_MESSAGE = "send_message"

# --- СХЕМЫ СЛУЖБ ---
SEND_PHOTO_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_ids,
    vol.Exclusive("url", "source"): cv.url,
    vol.Exclusive("file", "source"): cv.string,
    vol.Optional("message", default=""): cv.string,
    vol.Optional("keyboard"): dict,
    vol.Optional("reply_to"): cv.positive_int,
})

SEND_FILE_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_ids,
    vol.Required("file"): cv.string,
    vol.Optional("message", default=""): cv.string,
    vol.Optional("keyboard"): dict,
    vol.Optional("reply_to"): cv.positive_int,
})

SEND_MESSAGE_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_ids,
    vol.Required("message"): cv.string,
    vol.Optional("title"): cv.string,
    vol.Optional("keyboard"): dict,
    vol.Optional("reply_to"): cv.positive_int,
})

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("lp_managers", {})
    hass.data[DOMAIN][entry.entry_id] = {"data": entry.data}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    if entry.data.get(CONF_MODE) == MODE_LONGPOLL:
        group_id: int = entry.data[CONF_GROUP_ID]
        lp_managers: dict = hass.data[DOMAIN]["lp_managers"]
        if group_id not in lp_managers:
            manager = VkLongPollManager(hass, entry.data[CONF_ACCESS_TOKEN], group_id)
            lp_managers[group_id] = {"manager": manager, "refcount": 1}
            manager.start()
        else:
            lp_managers[group_id]["refcount"] += 1
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_MODE) == MODE_LONGPOLL:
        group_id: int = entry.data[CONF_GROUP_ID]
        lp_managers: dict = hass.data[DOMAIN]["lp_managers"]
        if group_id in lp_managers:
            lp_managers[group_id]["refcount"] -= 1
            if lp_managers[group_id]["refcount"] <= 0:
                await lp_managers[group_id]["manager"].stop()
                del lp_managers[group_id]
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok: hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE): return

    # --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ОТПРАВКИ ---
    async def _vk_send(access_token, peer_id, params):
        session = async_get_clientsession(hass)
        params.update({"access_token": access_token, "peer_id": peer_id, "random_id": random.randint(0, 2**31), "v": VK_API_VERSION})
        async with session.post(VK_API_URL, data=params) as resp:
            data = await resp.json()
            if "error" in data: raise HomeAssistantError(f"VK API error: {data['error']}")
            return data

    # --- SEND MESSAGE ---
    async def handle_send_message(call: ServiceCall):
        msg = f"{call.data['title']}\n{call.data['message']}" if call.data.get("title") else call.data["message"]
        params = {"message": msg}
        if call.data.get("keyboard"): params["keyboard"] = json.dumps(call.data["keyboard"], ensure_ascii=False)
        if call.data.get("reply_to"): params["reply_to"] = call.data["reply_to"]
        
        ent_reg = er.async_get(hass)
        for eid in call.data["entity_id"]:
            entry = ent_reg.async_get(eid)
            if entry and entry.config_entry_id in hass.data[DOMAIN]:
                d = hass.data[DOMAIN][entry.config_entry_id]["data"]
                await _vk_send(d[CONF_ACCESS_TOKEN], d[CONF_PEER_ID], params)

    hass.services.async_register(DOMAIN, SERVICE_SEND_MESSAGE, handle_send_message, schema=SEND_MESSAGE_SCHEMA)

    # --- SEND PHOTO ---
    async def handle_send_photo(call: ServiceCall):
        ent_reg = er.async_get(hass)
        for eid in call.data["entity_id"]:
            entry = ent_reg.async_get(eid)
            if entry and entry.config_entry_id in hass.data[DOMAIN]:
                d = hass.data[DOMAIN][entry.config_entry_id]["data"]
                att = await async_upload_photo(hass, d[CONF_ACCESS_TOKEN], d[CONF_PEER_ID], url=call.data.get("url"), filepath=call.data.get("file"))
                params = {"attachment": att, "message": call.data.get("message", "")}
                if call.data.get("keyboard"): params["keyboard"] = json.dumps(call.data["keyboard"], ensure_ascii=False)
                if call.data.get("reply_to"): params["reply_to"] = call.data["reply_to"]
                await _vk_send(d[CONF_ACCESS_TOKEN], d[CONF_PEER_ID], params)

    hass.services.async_register(DOMAIN, SERVICE_SEND_PHOTO, handle_send_photo, schema=SEND_PHOTO_SCHEMA)

    # --- SEND FILE ---
    async def handle_send_file(call: ServiceCall):
        ent_reg = er.async_get(hass)
        for eid in call.data["entity_id"]:
            entry = ent_reg.async_get(eid)
            if entry and entry.config_entry_id in hass.data[DOMAIN]:
                d = hass.data[DOMAIN][entry.config_entry_id]["data"]
                att = await async_upload_file(hass, d[CONF_ACCESS_TOKEN], d[CONF_PEER_ID], call.data["file"])
                params = {"attachment": att, "message": call.data.get("message", "")}
                if call.data.get("keyboard"): params["keyboard"] = json.dumps(call.data["keyboard"], ensure_ascii=False)
                if call.data.get("reply_to"): params["reply_to"] = call.data["reply_to"]
                await _vk_send(d[CONF_ACCESS_TOKEN], d[CONF_PEER_ID], params)

    hass.services.async_register(DOMAIN, SERVICE_SEND_FILE, handle_send_file, schema=SEND_FILE_SCHEMA)

    # --- WALL POST ---
    async def handle_wall_post(call: ServiceCall) -> ServiceResponse:
        ent_reg = er.async_get(hass)
        session = async_get_clientsession(hass)
        results = {}
        for eid in call.data["entity_id"]:
            entry = ent_reg.async_get(eid)
            if entry and entry.config_entry_id in hass.data[DOMAIN]:
                d = hass.data[DOMAIN][entry.config_entry_id]["data"]
                params = {"access_token": d[CONF_ACCESS_TOKEN], "owner_id": f"-{d[CONF_GROUP_ID]}", "from_group": 1, "message": call.data.get("message", ""), "v": VK_API_VERSION}
                if call.data.get("file"):
                    params["attachments"] = await async_upload_file(hass, d[CONF_ACCESS_TOKEN], d[CONF_PEER_ID], call.data["file"])
                async with session.post(VK_API_WALL_POST, data=params) as resp:
                    res = await resp.json()
                    if "error" in res: raise HomeAssistantError(f"Wall error: {res['error']}")
                    results[eid] = res["response"]["post_id"]
        return {"post_id": next(iter(results.values()))} if len(results) == 1 else {"post_ids": results}

    hass.services.async_register(DOMAIN, SERVICE_WALL_POST, handle_wall_post, schema=vol.Schema({vol.Required("entity_id"): cv.entity_ids, vol.Optional("message", default=""): cv.string, vol.Optional("file"): cv.string}), supports_response=SupportsResponse.OPTIONAL)
