from __future__ import annotations

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import VK_API_PHOTO_SAVE, VK_API_PHOTO_UPLOAD_SERVER, VK_API_VERSION


async def async_upload_photo(
    hass: HomeAssistant,
    access_token: str,
    peer_id: int,
    url: str | None = None,
    filepath: str | None = None,
) -> str:
    """Загружает фото в VK и возвращает строку вложения вида photo{owner_id}_{id}."""
    session = async_get_clientsession(hass)

    # Шаг 1: получить URL сервера для загрузки фото сообщения
    async with session.get(
        VK_API_PHOTO_UPLOAD_SERVER,
        params={"access_token": access_token, "peer_id": peer_id, "v": VK_API_VERSION},
    ) as resp:
        data = await resp.json()
    if "error" in data:
        raise HomeAssistantError(f"VK API error (getMessagesUploadServer): {data['error']}")
    upload_url = data["response"]["upload_url"]

    # Шаг 2: получить байты фото — либо скачать по URL, либо прочитать локальный файл
    if url:
        async with session.get(url) as resp:
            photo_bytes = await resp.read()
        filename = url.rstrip("/").split("/")[-1] or "photo.jpg"
    else:
        if not hass.config.is_allowed_path(filepath):
            raise HomeAssistantError(
                f"Path '{filepath}' is not allowed. Add it to allowlist_external_dirs."
            )
        photo_bytes = await hass.async_add_executor_job(
            lambda: open(filepath, "rb").read()  # noqa: WPS515
        )
        filename = filepath.split("/")[-1]

    # Шаг 3: загрузить фото на сервер VK через multipart/form-data
    form = aiohttp.FormData()
    form.add_field("photo", photo_bytes, filename=filename, content_type="image/jpeg")
    async with session.post(upload_url, data=form) as resp:
        upload_result = await resp.json()

    # Шаг 4: сохранить загруженное фото и получить его идентификатор
    async with session.get(
        VK_API_PHOTO_SAVE,
        params={
            "access_token": access_token,
            "v": VK_API_VERSION,
            "server": upload_result["server"],
            "photo": upload_result["photo"],
            "hash": upload_result["hash"],
        },
    ) as resp:
        data = await resp.json()
    if "error" in data:
        raise HomeAssistantError(f"VK API error (saveMessagesPhoto): {data['error']}")

    photo = data["response"][0]
    return f"photo{photo['owner_id']}_{photo['id']}"
