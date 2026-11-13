"""Route Alarmo state changes and failed arming events to the player."""

import asyncio
import logging
from collections.abc import Callable, Mapping
from typing import Any

from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event

from . import history
from .const import ALARM, RULES, SENSOR_RULES, Priority
from .media import resolve
from .playback import Playback

_LOGGER = logging.getLogger(__name__)

# Explicit polarity: raw Zigbee contact=true can mean CLOSED, unlike HA on=open.
CLOSED_STATES = {"on": "off", "off": "on", "true": "false", "false": "true",
                 "open": "closed", "closed": "open"}


def alarm_event(state: str) -> str:
    """Treat all armed modes as the same sound event."""
    return "armed" if state.startswith("armed_") else state


class AlarmSounds:
    """Play the rules configured for one alarm entity."""

    def __init__(
        self, hass: HomeAssistant, playback: Playback, options: Mapping[str, Any]
    ) -> None:
        self.hass = hass
        self.playback = playback
        self.alarm = options.get(ALARM)
        self.rules = options.get(RULES, {})
        self.sensor_rules = options.get(SENSOR_RULES, {})
        self._lock = asyncio.Lock()
        self._unsubscribers: list[Callable[[], None]] = []

    def subscribe(self) -> list[Callable[[], None]]:
        """Keep standalone sensor rules independent of the optional alarm panel."""
        subscriptions = [
            async_track_state_change_event(self.hass, [self.alarm], self._state_changed),
            self.hass.bus.async_listen("alarmo_failed_to_arm", self._failed_to_arm),
        ] if self.alarm else []
        opening_sensors = list(self.sensor_rules)
        if opening_sensors:
            subscriptions.append(async_track_state_change_event(
                self.hass, opening_sensors, self._sensor_opened,
            ))
        return subscriptions

    async def _sensor_opened(self, event: Event) -> None:
        """Play distinct sounds for real activation and deactivation transitions."""
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if old is None or new is None or old.state == new.state:
            return
        entity_id = event.data["entity_id"]
        async with self._lock:
            rule = self.sensor_rules.get(entity_id)
            if not rule:
                return
            attempt = history.begin(self.hass, entity_id, "Audio automático", rule.get("priority", "high"), old.state, new.state)
            if not rule.get("enabled", True):
                history.finish(attempt, "omitted", "Aviso de audio desactivado.")
                return
            open_state = rule.get("open_state", "on")
            closed_state = rule.get("closed_state", CLOSED_STATES.get(open_state))
            previous, updated = old.state.casefold(), new.state.casefold()
            if closed_state is None or (previous, updated) not in {
                (closed_state, open_state), (open_state, closed_state),
            }:
                history.finish(attempt, "omitted", "La transición no coincide con los estados de apertura/cierre configurados.")
                _LOGGER.debug("Sensor %s %s -> %s ignored: expected %s/%s", entity_id,
                              old.state, new.state, open_state, closed_state)
                return
            opening = updated == open_state
            mode = rule.get("on_open" if opening else "on_close", "never")
            if mode not in {"disarmed", "always"}:
                history.finish(attempt, "omitted", "No hay aviso automático habilitado para esta apertura o cierre.")
                _LOGGER.debug("Sensor %s %s -> %s ignored: mode=%s", entity_id, old.state, new.state, mode)
                return
            panel = self.hass.states.get(self.alarm) if self.alarm else None
            if mode == "disarmed" and (panel is None or panel.state != "disarmed"):
                history.finish(attempt, "omitted", "Requiere Alarmo desarmado; el panel no está desarmado o no está disponible.")
                _LOGGER.debug("Sensor %s %s -> %s ignored: panel=%s", entity_id, old.state, new.state,
                              panel.state if panel else "missing")
                return
            current = self.hass.states.get(entity_id)
            if current is None or current.state != new.state:
                history.finish(attempt, "omitted", "El sensor ya cambió de estado de nuevo.")
                _LOGGER.debug("Sensor %s %s -> %s ignored: transition superseded", entity_id, old.state, new.state)
                return
            selection = rule.get("sound" if opening else "close_sound")
            if not selection:
                history.finish(attempt, "omitted", "No hay audio asignado para esta apertura o cierre.")
                _LOGGER.debug("Sensor %s %s -> %s ignored: no sound assigned", entity_id, old.state, new.state)
            if selection:
                _LOGGER.debug("Sensor %s %s -> %s matched: mode=%s", entity_id, old.state, new.state, mode)
                kind = "sensor_open" if opening else "sensor_close"
                await self._play({**rule, "sound": selection}, f"{kind}:{entity_id}", attempt=attempt)

    def start(self) -> None:
        """Own subscriptions so options can replace them without reloading playback."""
        self._unsubscribers = self.subscribe()

    def close(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    async def update_options(self, options: Mapping[str, Any]) -> None:
        """Apply assignments live, stopping only an obsolete alarm siren."""
        async with self._lock:
            panel_changed = self.alarm != options.get(ALARM)
            siren_changed = self.rules.get("triggered") != options.get(RULES, {}).get("triggered")
            if panel_changed or siren_changed:
                await self.playback.stop(owner="triggered")
            self.close()
            self.alarm = options.get(ALARM)
            self.rules = options.get(RULES, {})
            self.sensor_rules = options.get(SENSOR_RULES, {})
            self.start()
        if panel_changed or siren_changed:
            await self.restore_siren()

    async def restore_siren(self) -> None:
        """Restore a repeating siren after setup if the panel is still triggered."""
        async with self._lock:
            state = self.hass.states.get(self.alarm) if self.alarm else None
            rule = self.rules.get("triggered")
            if state and state.state == "triggered" and rule and rule.get("repeat"):
                await self._play(rule, "triggered")

    async def _state_changed(self, event: Event) -> None:
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        if new_state is None:
            return
        kind = alarm_event(new_state.state)
        if old_state is None and kind != "triggered":
            return
        if old_state and alarm_event(old_state.state) == kind:
            return
        async with self._lock:
            if event.data.get("entity_id") != self.alarm:
                return
            # Ignore queued transitions that the alarm has already left.
            current = self.hass.states.get(self.alarm)
            if current is None or alarm_event(current.state) != kind:
                return
            if kind in {"disarmed", "armed", "arming", "pending"}:
                await self.playback.stop(owner="triggered")
                await self.playback.stop(owner="failed_to_arm")
                if old_state and alarm_event(old_state.state) != "triggered":
                    await self.playback.stop(owner=alarm_event(old_state.state))
            if rule := self.rules.get(kind):
                await self._play(rule, kind)

    async def _failed_to_arm(self, event: Event) -> None:
        # Alarmo versions may omit entity_id from this event.
        if event.data.get("entity_id") not in {None, self.alarm}:
            return
        async with self._lock:
            if not self.alarm or event.data.get("entity_id") not in {None, self.alarm}:
                return
            sensors = event.data.get("sensors") or []
            if event.data.get("reason") == "open_sensors":
                matches = [
                    (entity_id, self.sensor_rules[entity_id])
                    for entity_id in sensors
                    if entity_id in self.sensor_rules
                    and self.sensor_rules[entity_id].get("failed_to_arm", True)
                    and self.sensor_rules[entity_id].get("sound")
                    and self.sensor_rules[entity_id].get("enabled", True)
                ]
                if matches:
                    sensor, rule = max(matches, key=lambda item: Priority[item[1]["priority"].upper()])
                    attempt = history.begin(self.hass, sensor, "Audio por fallo al armar Alarmo", rule["priority"])
                    await self._play(rule, "failed_to_arm", attempt=attempt)
                    return
            if rule := self.rules.get("failed_to_arm"):
                await self._play(rule, "failed_to_arm")

    async def _play(self, rule: dict, kind: str, *, attempt=None) -> None:
        if not rule.get("enabled", True):
            return
        priority = Priority[rule["priority"].upper()]
        try:
            sound = await resolve(self.hass, rule["sound"]["media_content_id"], None)
            result = await self.playback.play(
                sound, priority, repeat=kind == "triggered" and rule.get("repeat", False),
                owner=kind,
                **({"on_result": history.playback_result(attempt)} if attempt else {}),
            )
            if attempt:
                history.accepted(attempt, result)
        except (HomeAssistantError, OSError) as err:
            history.finish(attempt, "error", "No se pudo preparar o reproducir el audio. Revisa los registros.")
            _LOGGER.warning("Could not play Alarmo event %s (%s)", kind, type(err).__name__)
