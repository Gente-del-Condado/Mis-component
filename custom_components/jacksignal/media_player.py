"""Expose the jack as a native Home Assistant media player."""

import asyncio
from datetime import timedelta
from typing import Any

import pulsectl

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import Priority
from .media import browse_audio, error, resolve
from .playback import Playback
from .volume import output_volume


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[Playback], async_add_entities: AddEntitiesCallback
) -> None:
    """Register the player."""
    async_add_entities([JackPlayer(entry.runtime_data, entry.entry_id)])


class JackPlayer(MediaPlayerEntity):
    """The Raspberry Pi analog output."""

    _attr_name = "JackSignal"
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_should_poll = False
    _attr_supported_features = (
        MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
    )

    def __init__(self, playback: Playback, entry_id: str) -> None:
        self._playback = playback
        self._attr_unique_id = entry_id
        self._volume_lock = asyncio.Lock()

    async def async_added_to_hass(self) -> None:
        self._playback.changed = self.async_write_ha_state
        await self._update_volume()
        self.async_on_remove(async_track_time_interval(
            self.hass, self._update_volume, timedelta(seconds=30),
        ))

    async def async_will_remove_from_hass(self) -> None:
        self._playback.changed = lambda: None

    @property
    def state(self) -> MediaPlayerState:
        if self._playback.sound is None:
            return MediaPlayerState.IDLE
        if self._playback.paused:
            return MediaPlayerState.PAUSED
        return MediaPlayerState.PLAYING

    @property
    def media_title(self) -> str | None:
        sound = self._playback.sound
        return sound.title if sound else None

    async def _update_volume(self, _now=None) -> None:
        async with self._volume_lock:
            try:
                volume = await self.hass.async_add_executor_job(output_volume)
            except (pulsectl.PulseError, OSError):
                self._attr_volume_level = None
                self._attr_is_volume_muted = None
            else:
                self._attr_volume_level = volume.level
                self._attr_is_volume_muted = volume.muted
            self.async_write_ha_state()

    async def _set_volume(self, level=None, muted=None) -> None:
        async with self._volume_lock:
            try:
                volume = await self.hass.async_add_executor_job(output_volume, level, muted)
            except (pulsectl.PulseError, OSError) as err:
                raise error("audio_unavailable") from err
            self._attr_volume_level = volume.level
            self._attr_is_volume_muted = volume.muted
            self.async_write_ha_state()

    async def async_set_volume_level(self, volume: float) -> None:
        await self._set_volume(level=volume)

    async def async_mute_volume(self, mute: bool) -> None:
        await self._set_volume(muted=mute)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "priority": self._playback.priority.name.lower(),
            "alarm_event": self._playback.owner,
        }

    async def async_media_play(self) -> None:
        await self._playback.set_paused(False)

    async def async_media_pause(self) -> None:
        await self._playback.set_paused(True)

    async def async_media_stop(self) -> None:
        await self._playback.stop()

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        sound = await resolve(self.hass, media_id, self.entity_id)
        try:
            await self._playback.play(sound, Priority.LOW)
        except OSError as err:
            raise error("ffmpeg_unavailable") from err

    async def async_browse_media(
        self, media_content_type: str | None = None, media_content_id: str | None = None
    ) -> BrowseMedia:
        return await media_source.async_browse_media(
            self.hass, media_content_id, content_filter=browse_audio
        )
