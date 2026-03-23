from __future__ import annotations

import random

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ACCESS_TOKEN, CONF_PEER_ID, DOMAIN, VK_API_URL, VK_API_VERSION
from .helpers import async_upload_photo

PLATFORMS = [Platform.NOTIFY]

SERVICE_SEND_PHOTO = "send_photo"

SEND_PHOTO_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_ids,
        vol.Exclusive("url", "source"): cv.url,
        vol.Exclusive("file", "source"): cv.string,
        vol.Optional("message", default=""): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND_PHOTO):
        return

    async def handle_send_photo(call: ServiceCall) -> None:
        entity_ids: list[str] = call.data["entity_id"]
        url: str | None = call.data.get("url")
        filepath: str | None = call.data.get("file")
        caption: str = call.data.get("message", "")

        ent_reg = er.async_get(hass)
        session = async_get_clientsession(hass)

        for entity_id in entity_ids:
            entry_entity = ent_reg.async_get(entity_id)
            if entry_entity is None or entry_entity.config_entry_id not in hass.data[DOMAIN]:
                raise HomeAssistantError(f"Entity {entity_id} not found or not a VK Notify entity")

            entry_data = hass.data[DOMAIN][entry_entity.config_entry_id]
            access_token: str = entry_data[CONF_ACCESS_TOKEN]
            peer_id: int = entry_data[CONF_PEER_ID]

            attachment = await async_upload_photo(hass, access_token, peer_id, url=url, filepath=filepath)

            params = {
                "access_token": access_token,
                "peer_id": peer_id,
                "attachment": attachment,
                "message": caption,
                "random_id": random.randint(0, 2**31),
                "v": VK_API_VERSION,
            }
            async with session.get(VK_API_URL, params=params) as resp:
                data = await resp.json()
            if "error" in data:
                raise HomeAssistantError(f"VK API error (messages.send): {data['error']}")

    hass.services.async_register(DOMAIN, SERVICE_SEND_PHOTO, handle_send_photo, schema=SEND_PHOTO_SCHEMA)
