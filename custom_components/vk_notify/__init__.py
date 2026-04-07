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
SERVICE_SEND_MESSAGE = "send_message"  # ДОБАВЛЕНО: новый сервис для сообщений

SEND_PHOTO_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_ids,
        vol.Exclusive("url", "source"): cv.url,   # url и file взаимоисключающие
        vol.Exclusive("file", "source"): cv.string,
        vol.Optional("message", default=""): cv.string,
        vol.Optional("keyboard"): dict,  # поддержка клавиатуры
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    # lp_managers — общий словарь {group_id: {manager, refcount}} для всех записей
    hass.data[DOMAIN].setdefault("lp_managers", {})
    hass.data[DOMAIN][entry.entry_id] = {"data": entry.data}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)

    if entry.data.get(CONF_MODE) == MODE_LONGPOLL:
        group_id: int = entry.data[CONF_GROUP_ID]
        lp_managers: dict = hass.data[DOMAIN]["lp_managers"]

        if group_id in lp_managers:
            # Менеджер для этого сообщества уже запущен другой записью — просто увеличиваем счётчик
            lp_managers[group_id]["refcount"] += 1
        else:
            # Первая запись с данным group_id — создаём и запускаем менеджер
            manager = VkLongPollManager(
                hass,
                access_token=entry.data[CONF_ACCESS_TOKEN],
                group_id=group_id,
            )
            lp_managers[group_id] = {"manager": manager, "refcount": 1}
            manager.start()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_MODE) == MODE_LONGPOLL:
        group_id: int = entry.data[CONF_GROUP_ID]
        lp_managers: dict = hass.data[DOMAIN]["lp_managers"]
        if group_id in lp_managers:
            lp_managers[group_id]["refcount"] -= 1
            if lp_managers[group_id]["refcount"] <= 0:
                # Последняя запись с этим group_id выгружена — останавливаем менеджер
                await lp_managers[group_id]["manager"].stop()
                del lp_managers[group_id]

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    """Зарегистрировать сервисы интеграции. Вызывается при каждой загрузке записи,
    но реальная регистрация происходит только один раз."""
    
    if hass.services.has_service(DOMAIN, SERVICE_SEND_PHOTO):
        return

    async def handle_send_photo(call: ServiceCall) -> None:
        entity_ids: list[str] = call.data["entity_id"]
        url: str | None = call.data.get("url")
        filepath: str | None = call.data.get("file")
        caption: str = call.data.get("message", "")
        keyboard: dict | None = call.data.get("keyboard")

        ent_reg = er.async_get(hass)
        session = async_get_clientsession(hass)

        for entity_id in entity_ids:
            entry_entity = ent_reg.async_get(entity_id)
            if entry_entity is None or entry_entity.config_entry_id not in hass.data[DOMAIN]:
                raise HomeAssistantError(f"Entity {entity_id} not found or not a VK Notify entity")

            entry_data = hass.data[DOMAIN][entry_entity.config_entry_id]["data"]
            access_token: str = entry_data[CONF_ACCESS_TOKEN]
            peer_id: int = entry_data[CONF_PEER_ID]

            # Загружаем фото в VK и получаем строку вложения
            attachment = await async_upload_photo(hass, access_token, peer_id, url=url, filepath=filepath)

            params = {
                "access_token": access_token,
                "peer_id": peer_id,
                "attachment": attachment,
                "message": caption,
                "random_id": random.randint(0, 2**31),
                "v": VK_API_VERSION,
            }
            if keyboard:
                params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)

            async with session.get(VK_API_URL, params=params) as resp:
                data = await resp.json()
            if "error" in data:
                raise HomeAssistantError(f"VK API error (messages.send): {data['error']}")

    hass.services.async_register(DOMAIN, SERVICE_SEND_PHOTO, handle_send_photo, schema=SEND_PHOTO_SCHEMA)

    if hass.services.has_service(DOMAIN, SERVICE_SEND_FILE):
        return

    SEND_FILE_SCHEMA = vol.Schema(
        {
            vol.Required("entity_id"): cv.entity_ids,
            vol.Required("file"): cv.string,
            vol.Optional("message", default=""): cv.string,
            vol.Optional("keyboard"): dict,
        }
    )

    async def handle_send_file(call: ServiceCall) -> None:
        entity_ids: list[str] = call.data["entity_id"]
        filepath: str = call.data["file"]
        caption: str = call.data.get("message", "")
        keyboard: dict | None = call.data.get("keyboard")

        ent_reg = er.async_get(hass)
        session = async_get_clientsession(hass)

        for entity_id in entity_ids:
            entry_entity = ent_reg.async_get(entity_id)
            if entry_entity is None or entry_entity.config_entry_id not in hass.data[DOMAIN]:
                raise HomeAssistantError(f"Entity {entity_id} not found or not a VK Notify entity")

            entry_data = hass.data[DOMAIN][entry_entity.config_entry_id]["data"]
            access_token: str = entry_data[CONF_ACCESS_TOKEN]
            peer_id: int = entry_data[CONF_PEER_ID]

            # Загружаем файл в VK и получаем строку вложения
            attachment = await async_upload_file(hass, access_token, peer_id, filepath)

            params = {
                "access_token": access_token,
                "peer_id": peer_id,
                "attachment": attachment,
                "message": caption,
                "random_id": random.randint(0, 2**31),
                "v": VK_API_VERSION,
            }
            if keyboard:
                params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)

            async with session.get(VK_API_URL, params=params) as resp:
                data = await resp.json()
            if "error" in data:
                raise HomeAssistantError(f"VK API error (messages.send): {data['error']}")

    hass.services.async_register(DOMAIN, SERVICE_SEND_FILE, handle_send_file, schema=SEND_FILE_SCHEMA)

    if hass.services.has_service(DOMAIN, SERVICE_WALL_POST):
        return

    WALL_POST_SCHEMA = vol.Schema(
        {
            vol.Required("entity_id"): cv.entity_ids,
            vol.Optional("message", default=""): cv.string,
            vol.Optional("file"): cv.string,
        }
    )

    async def handle_wall_post(call: ServiceCall) -> ServiceResponse:
        entity_ids: list[str] = call.data["entity_id"]
        message: str = call.data.get("message", "")
        filepath: str | None = call.data.get("file")

        ent_reg = er.async_get(hass)
        session = async_get_clientsession(hass)
        post_ids: dict[str, int] = {}

        for entity_id in entity_ids:
            entry_entity = ent_reg.async_get(entity_id)
            if entry_entity is None or entry_entity.config_entry_id not in hass.data[DOMAIN]:
                raise HomeAssistantError(f"Entity {entity_id} not found or not a VK Notify entity")

            entry_data = hass.data[DOMAIN][entry_entity.config_entry_id]["data"]
            access_token: str = entry_data[CONF_ACCESS_TOKEN]
            group_id: int = entry_data[CONF_GROUP_ID]
            peer_id: int = entry_data[CONF_PEER_ID]
            attachments: list[str] = []

            if filepath:
                if filepath.lower().endswith(".ogg"):
                    raise HomeAssistantError("OGG files cannot be attached to wall posts (VK API limitation).")
                file_attachment = await async_upload_file(hass, access_token, peer_id, filepath)
                attachments.append(file_attachment)

            params = {
                "access_token": access_token,
                "owner_id": f"-{group_id}",
                "from_group": 1,
                "message": message,
                "v": VK_API_VERSION,
            }
            if attachments:
                params["attachments"] = ",".join(attachments)

            async with session.post(VK_API_WALL_POST, data=params) as resp:
                data = await resp.json()
            if "error" in data:
                raise HomeAssistantError(f"VK API error (wall.post): {data['error']}")

            post_ids[entity_id] = data["response"]["post_id"]

        if len(post_ids) == 1:
            return {"post_id": next(iter(post_ids.values()))}
        return {"post_ids": post_ids}

    hass.services.async_register(
        DOMAIN, SERVICE_WALL_POST, handle_wall_post,
        schema=WALL_POST_SCHEMA, supports_response=SupportsResponse.OPTIONAL,
    )

    # --- ДОБАВЛЕНО: Новый сервис vk_notify.send_message ---
    if hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE):
        return

    SEND_MESSAGE_SCHEMA = vol.Schema(
        {
            vol.Required("entity_id"): cv.entity_ids,
            vol.Required("message"): cv.string,
            vol.Optional("title"): cv.string,
            vol.Optional("keyboard"): dict,
        }
    )

    async def handle_send_message(call: ServiceCall) -> None:
        entity_ids: list[str] = call.data["entity_id"]
        message: str = call.data["message"]
        title: str | None = call.data.get("title")
        keyboard: dict | None = call.data.get("keyboard")

        # Добавляем заголовок, если он передан
        if title:
            message = f"{title}\n{message}"

        ent_reg = er.async_get(hass)
        session = async_get_clientsession(hass)

        for entity_id in entity_ids:
            entry_entity = ent_reg.async_get(entity_id)
            if entry_entity is None or entry_entity.config_entry_id not in hass.data[DOMAIN]:
                raise HomeAssistantError(f"Entity {entity_id} not found or not a VK Notify entity")

            entry_data = hass.data[DOMAIN][entry_entity.config_entry_id]["data"]
            access_token: str = entry_data[CONF_ACCESS_TOKEN]
            peer_id: int = entry_data[CONF_PEER_ID]

            params = {
                "access_token": access_token,
                "peer_id": peer_id,
                "message": message,
                "random_id": random.randint(0, 2**31),
                "v": VK_API_VERSION,
            }
            
            if keyboard:
                params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)

            # Используем session.post, так как текст и клавиатура могут быть объемными
            async with session.post(VK_API_URL, data=params) as resp:
                data = await resp.json()
            if "error" in data:
                raise HomeAssistantError(f"VK API error (messages.send): {data['error']}")

    hass.services.async_register(DOMAIN, SERVICE_SEND_MESSAGE, handle_send_message, schema=SEND_MESSAGE_SCHEMA)
