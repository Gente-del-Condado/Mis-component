"""Resolve Home Assistant media for FFmpeg."""

from pathlib import Path
from urllib.parse import unquote, urlsplit

from homeassistant.components import media_source
from homeassistant.components.media_player import BrowseMedia, async_process_play_media_url
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, LOCAL_PREFIX
from .playback import Sound

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".opus", ".flac", ".m4a", ".aac"}


def error(key: str) -> HomeAssistantError:
    """Return a localized playback error."""
    return HomeAssistantError(translation_domain=DOMAIN, translation_key=key)


def _local_sound(directory: str, relative_path: str) -> Sound:
    """Resolve inside a configured media directory, including symlink checks."""
    try:
        root = Path(directory).resolve()
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() not in AUDIO_EXTENSIONS:
            raise error("invalid_media")
        if not path.is_file():
            raise error("missing_media")
    except (OSError, ValueError, RuntimeError) as err:
        raise error("invalid_media") from err
    return Sound(str(path), path.name, local=True)


async def resolve(hass: HomeAssistant, media_id: str, entity_id: str | None) -> Sound:
    """Read local media directly and accept Home Assistant audio sources and URLs."""
    if media_id.startswith(LOCAL_PREFIX):
        directory_id, _, relative_path = media_id[len(LOCAL_PREFIX):].partition("/")
        directory = hass.config.media_dirs.get(directory_id)
        if not directory or not relative_path:
            raise error("invalid_media")
        return await hass.async_add_executor_job(_local_sound, directory, relative_path)

    if media_source.is_media_source_id(media_id):
        try:
            media_id = (await media_source.async_resolve_media(hass, media_id, entity_id)).url
        except media_source.MediaSourceError as err:
            raise error("missing_media") from err

    media_id = async_process_play_media_url(hass, media_id)
    url = urlsplit(media_id)
    if url.scheme not in {"http", "https"} or not url.hostname:
        raise error("invalid_media")
    return Sound(media_id, unquote(Path(url.path).name) or url.hostname, local=False)


def browse_audio(item: BrowseMedia) -> bool:
    """Keep folders and playable audio in the picker."""
    media_type = item.media_content_type
    return item.can_expand or media_type in {"music", "audio", "channel"} or (
        isinstance(media_type, str) and media_type.startswith("audio/")
    )
