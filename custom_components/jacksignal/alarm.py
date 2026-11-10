"""Route Alarmo state changes and failed arming events to the player."""

import asyncio
from collections.abc import Callable, Mapping
import logging
from typing import Any

from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event

from .const import ALARM, RULES, SENSOR_RULES, Priority
from .media import resolve
from .playback import Playback

_LOGGER = logging.getLogger(__name__)


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
        """Subscribe only if the user selected an alarm panel."""
        if not self.alarm:
            return []
        return [
            async_track_state_change_event(self.hass, [self.alarm], self._state_changed),
            self.hass.bus.async_listen("alarmo_failed_to_arm", self._failed_to_arm),
        ]

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
                    self.sensor_rules[entity_id]
                    for entity_id in sensors
                    if entity_id in self.sensor_rules
                ]
                if matches:
                    rule = max(matches, key=lambda item: Priority[item["priority"].upper()])
                    await self._play(rule, "failed_to_arm")
                    return
            if rule := self.rules.get("failed_to_arm"):
                await self._play(rule, "failed_to_arm")

    async def _play(self, rule: dict, kind: str) -> None:
        priority = Priority[rule["priority"].upper()]
        try:
            sound = await resolve(self.hass, rule["sound"]["media_content_id"], None)
            await self.playback.play(
                sound, priority, repeat=kind == "triggered" and rule.get("repeat", False),
                owner=kind,
            )
        except (HomeAssistantError, OSError) as err:
            _LOGGER.warning("Could not play Alarmo event %s (%s)", kind, type(err).__name__)
