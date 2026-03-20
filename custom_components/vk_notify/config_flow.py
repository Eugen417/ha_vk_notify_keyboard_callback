from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ACCESS_TOKEN, CONF_PEER_ID, DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_PEER_ID): int,
        vol.Optional("name", default="VK Notify"): str,
    }
)


async def _validate_token(hass, access_token: str) -> bool:
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            "https://api.vk.com/method/users.get",
            params={"access_token": access_token, "v": "5.199"},
        ) as resp:
            data = await resp.json()
            return "error" not in data
    except Exception:
        return False


class VkNotifyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            try:
                valid = await _validate_token(self.hass, user_input[CONF_ACCESS_TOKEN])
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                if not valid:
                    errors["base"] = "invalid_token"
                else:
                    return self.async_create_entry(
                        title=user_input.get("name", "VK Notify"),
                        data=user_input,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "docs_url": "https://udocs.ru/posts/home-assistant/integrations/otpravka-uvedomleniy-v-vk"
            },
        )
