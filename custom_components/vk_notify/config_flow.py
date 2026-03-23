from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ACCESS_TOKEN, CONF_PEER_ID, DOMAIN, VK_API_VERSION

STEP_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Optional("name", default="VK Notify"): str,
    }
)

VK_CONVERSATIONS_URL = "https://api.vk.com/method/messages.getConversations"


async def _validate_token(hass, access_token: str) -> bool:
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            "https://api.vk.com/method/users.get",
            params={"access_token": access_token, "v": VK_API_VERSION},
        ) as resp:
            data = await resp.json()
            return "error" not in data
    except Exception:
        return False


def _build_conversations(response: dict) -> tuple[dict[str, str], set[str]]:
    """Return (all_options, writable_ids).

    all_options  — {peer_id_str: label} for the dropdown (all chats).
    writable_ids — set of peer_id_str that can actually receive messages.
    """
    profiles = {p["id"]: f"{p['first_name']} {p['last_name']}" for p in response.get("profiles", [])}
    groups = {g["id"]: g["name"] for g in response.get("groups", [])}

    all_options: dict[str, str] = {}
    writable_ids: set[str] = set()

    for item in response.get("items", []):
        conv = item["conversation"]
        peer = conv["peer"]
        peer_id: int = peer["id"]
        peer_type: str = peer["type"]
        can_write: bool = conv.get("can_write", {}).get("allowed", True)

        if peer_type == "chat":
            name = conv.get("chat_settings", {}).get("title", f"Chat {peer_id}")
        elif peer_type == "user":
            name = profiles.get(peer_id, str(peer_id))
        elif peer_type == "group":
            name = groups.get(abs(peer_id), str(peer_id))
        else:
            name = str(peer_id)

        key = str(peer_id)
        label = f"{name} ({peer_id})" if can_write else f"⛔ {name} ({peer_id})"
        all_options[key] = label
        if can_write:
            writable_ids.add(key)

    return all_options, writable_ids


async def _get_conversations(hass, access_token: str) -> tuple[dict[str, str], set[str]]:
    """Fetch conversations from VK API and return (all_options, writable_ids)."""
    session = async_get_clientsession(hass)
    async with session.get(
        VK_CONVERSATIONS_URL,
        params={
            "access_token": access_token,
            "extended": 1,
            "count": 200,
            "v": VK_API_VERSION,
        },
    ) as resp:
        data = await resp.json()

    if "error" in data:
        return {}, set()

    return _build_conversations(data["response"])


class VkNotifyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._access_token: str = ""
        self._name: str = "VK Notify"

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
                    self._access_token = user_input[CONF_ACCESS_TOKEN]
                    self._name = user_input.get("name", "VK Notify")
                    return await self.async_step_select_chat()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_TOKEN_SCHEMA,
            errors=errors,
            description_placeholders={
                "docs_url": "https://udocs.ru/posts/home-assistant/integrations/otpravka-uvedomleniy-v-vk"
            },
        )

    async def async_step_select_chat(self, user_input=None):
        errors = {}
        all_options, writable_ids = await _get_conversations(self.hass, self._access_token)

        if not all_options:
            errors["base"] = "no_conversations"
        elif user_input is not None:
            if user_input[CONF_PEER_ID] not in writable_ids:
                errors[CONF_PEER_ID] = "chat_not_writable"
            else:
                return self.async_create_entry(
                    title=self._name,
                    data={
                        CONF_ACCESS_TOKEN: self._access_token,
                        CONF_PEER_ID: int(user_input[CONF_PEER_ID]),
                        "name": self._name,
                    },
                )

        return self.async_show_form(
            step_id="select_chat",
            data_schema=vol.Schema(
                {vol.Required(CONF_PEER_ID): vol.In(all_options)}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        self._access_token = entry.data[CONF_ACCESS_TOKEN]

        errors = {}
        all_options, writable_ids = await _get_conversations(self.hass, self._access_token)

        if not all_options:
            errors["base"] = "no_conversations"
        elif user_input is not None:
            if user_input[CONF_PEER_ID] not in writable_ids:
                errors[CONF_PEER_ID] = "chat_not_writable"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_PEER_ID: int(user_input[CONF_PEER_ID])},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_PEER_ID, default=str(entry.data[CONF_PEER_ID])): vol.In(all_options)}
            ),
            errors=errors,
        )
