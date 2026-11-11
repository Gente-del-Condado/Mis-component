"""JackSignal integration lifecycle and automation action."""

import shutil
from functools import partial

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import selector

from .alarm import AlarmSounds
from .const import DOMAIN, PLATFORMS, Priority
from .dlna import DlnaReceiver
from .media import error, resolve
from .playback import Playback
from .panel import async_setup_panel
from .selectors import media_selector, priority_selector, validation
from .speech import SensorSpeech

PLAY_SOUND = "play_sound"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry[Playback]) -> bool:
    """Set up playback, Alarmo and the shared action."""
    if not await hass.async_add_executor_job(shutil.which, "ffmpeg"):
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="ffmpeg_unavailable")

    playback = Playback(partial(entry.async_create_background_task, hass))
    entry.runtime_data = playback
    receiver = DlnaReceiver(playback, entry.entry_id)
    try:
        await receiver.configure(entry.options)
    except (OSError, ValueError) as err:
        await playback.close()
        raise ConfigEntryNotReady("Could not start the DLNA audio receiver") from err
    hass.data[DOMAIN] = receiver

    async def play_sound(call: ServiceCall) -> None:
        sound = await resolve(hass, call.data["sound"]["media_content_id"], None)
        try:
            await playback.play(sound, Priority[call.data["priority"].upper()])
        except OSError as err:
            raise error("ffmpeg_unavailable") from err

    async def stop(_event: Event) -> None:
        await receiver.close()
        await playback.close()

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await receiver.close()
        await playback.close()
        hass.data.pop(DOMAIN, None)
        raise
    hass.services.async_register(
        DOMAIN, PLAY_SOUND, play_sound,
        schema=validation.Schema({
            validation.Required("sound"): media_selector(),
            validation.Optional("priority", default="normal"): priority_selector(),
        }),
    )
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop))
    alarm = AlarmSounds(hass, playback, entry.options)
    alarm.start()
    entry.async_on_unload(alarm.close)
    speech = SensorSpeech(hass, playback, entry.options)
    hass.data["jacksignal_speech"] = speech
    entry.async_on_unload(lambda: hass.data.pop("jacksignal_speech", None))
    speech.start()
    entry.async_on_unload(speech.close)

    async def speak_sensor(call):
        try:
            await speech.say(call.data["sensor"])
        except OSError as err:
            raise error("ffmpeg_unavailable") from err

    hass.services.async_register(DOMAIN, "speak_sensor", speak_sensor, schema=validation.Schema({
        validation.Required("sensor"): selector.EntitySelector({"domain": ["sensor", "binary_sensor"]}),
    }))
    entry.async_on_unload(lambda: hass.services.async_remove(DOMAIN, "speak_sensor"))

    async def update_options(hass: HomeAssistant, updated: ConfigEntry) -> None:
        await receiver.configure(updated.options)
        await alarm.update_options(updated.options)
        speech.update_options(updated.options)

    entry.async_on_unload(entry.add_update_listener(update_options))
    await async_setup_panel(hass, entry)
    await alarm.restore_siren()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry[Playback]) -> bool:
    """Remove the action and release audio on unload."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.services.async_remove(DOMAIN, PLAY_SOUND)
    hass.services.async_remove(DOMAIN, "speak_sensor")
    if receiver := hass.data.pop(DOMAIN, None):
        await receiver.close()
    await entry.runtime_data.close()
    return True
