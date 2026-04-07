from __future__ import annotations

import json
import random

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ACCESS_TOKEN, CONF_PEER_ID, VK_API_URL, VK_API_VERSION


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([VkNotifyEntity(hass, entry)])


class VkNotifyEntity(NotifyEntity):
    _attr_has_entity_name = True
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._access_token: str = entry.data[CONF_ACCESS_TOKEN]
        self._peer_id: int = entry.data[CONF_PEER_ID]
        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.data.get("name", "VK Notify")

    async def async_send_message(self, message: str, title: str | None = None, **kwargs) -> None:
        # Если передан заголовок — добавляем его первой строкой
        if title:
            message = f"{title}\n{message}"

        session = async_get_clientsession(self.hass)
        params = {
            "access_token": self._access_token,
            "peer_id": self._peer_id,
            "message": message,
            # random_id предотвращает дублирование сообщений на стороне VK
            "random_id": random.randint(0, 2**31),
            "v": VK_API_VERSION,
        }

        # Извлекаем блок data из вызова службы HA
        data = kwargs.get("data")
        # Если в data передана keyboard, сериализуем её в JSON и добавляем к параметрам
        if data and "keyboard" in data:
            params["keyboard"] = json.dumps(data["keyboard"], ensure_ascii=False)

        try:
            async with session.get(VK_API_URL, params=params) as resp:
                data_json = await resp.json()
        except Exception as err:
            raise HomeAssistantError(f"Failed to connect to VK API: {err}") from err

        if "error" in data_json:
            raise HomeAssistantError(f"VK API error: {data_json['error']}")
