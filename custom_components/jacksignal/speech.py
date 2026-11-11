"""Configured sensor speech using Home Assistant TTS and JackSignal priorities."""

import asyncio
from dataclasses import replace
import logging
import math
import time

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event

from .const import Priority
from .media import error, resolve
from .playback import validate_speed

SPEECH_RULES = "speech_rules"
SPEECH_DEFAULTS = "speech_defaults"
VOICE_FIELDS = ("engine", "language", "voice", "speed")
_LOGGER = logging.getLogger(__name__)
INVALID = {"unknown", "unavailable", ""}


def piper_engines(hass):
    """Use the integration's original entity name, independent of user renames."""
    from homeassistant.helpers import entity_registry as er
    registry = er.async_get(hass)
    result = []
    for state in hass.states.async_all("tts"):
        entry = registry.async_get(state.entity_id)
        if entry and entry.platform == "wyoming" and (entry.original_name or "").casefold() == "piper":
            result.append(state.entity_id)
    return sorted(result)


def general_voice(hass, options):
    saved = options.get(SPEECH_DEFAULTS, {})
    candidates = piper_engines(hass)
    return {"engine": saved.get("engine") or (candidates[0] if len(candidates) == 1 else ""),
            "language": saved.get("language", ""), "voice": saved.get("voice", ""),
            "speed": saved.get("speed", 1.0)}


def effective_rule(hass, rule, options):
    if not rule.get("use_defaults", False):
        return dict(rule)
    return {**rule, **general_voice(hass, options)}


def suggested_state_labels(state):
    """Offer editable wording using HA binary sensor semantics, never entity names."""
    if state is None or state.domain != "binary_sensor":
        return {}
    device_class = state.attributes.get("device_class")
    words = {
        "window": ("abierta", "cerrada"),
        "door": ("abierta", "cerrada"),
        "garage_door": ("abierta", "cerrada"),
        "opening": ("abierto", "cerrado"),
        "power": ("encendido", "apagado"),
        "running": ("en marcha", "detenido"),
        "light": ("luz detectada", "sin luz"),
        "motion": ("movimiento detectado", "sin movimiento"),
        "occupancy": ("ocupado", "libre"),
        "connectivity": ("conectado", "desconectado"),
        "plug": ("enchufado", "desenchufado"),
        "lock": ("desbloqueado", "bloqueado"),
        None: ("encendido", "apagado"),
        "": ("encendido", "apagado"),
    }.get(device_class)
    if words is None:
        return {}
    return dict(zip(("on", "off"), words))


def message_for(state, rule):
    """Use ordinary text fields, never execute user-supplied templates."""
    if state is None or state.state in INVALID:
        raise error("speech_sensor_unavailable")
    unit = state.attributes.get("unit_of_measurement", "") if rule.get("unit", True) else ""
    return " ".join(str(part).strip() for part in (
        rule.get("before", ""), rule.get("state_labels", {}).get(state.state, state.state), unit, rule.get("after", ""),
    ) if part and str(part).strip())


def matches(old, new, rule):
    if old is None or new is None or old.state in INVALID or new.state in INVALID:
        return False
    if old.state == new.state:
        return False
    trigger = rule.get("trigger", "manual")
    if trigger == "change":
        return True
    if trigger not in {"above", "below"}:
        return False
    try:
        previous, current, threshold = float(old.state), float(new.state), float(rule["threshold"])
    except (ValueError, TypeError, KeyError):
        return False
    if not all(math.isfinite(value) for value in (previous, current, threshold)):
        return False
    return previous <= threshold < current if trigger == "above" else previous >= threshold > current


def preferred_language(provider):
    """Use the engine's exact language code; prefer Spain, then generic Spanish."""
    languages = list(provider.supported_languages or [])
    normalized = {language.replace("_", "-").lower(): language for language in languages}
    for candidate in ("es-es", "es"):
        if candidate in normalized:
            return normalized[candidate]
    return next((language for language in languages if language.replace("_", "-").lower().startswith("es-")), provider.default_language)


def voice_settings(provider, language=None, voice=None):
    """Resolve automatic Spanish and a matching voice without overriding explicit choices."""
    if not language:
        language = preferred_language(provider)
        if voice:
            # Older rules may have selected a voice while leaving language automatic.
            for candidate in dict.fromkeys([provider.default_language, *provider.supported_languages]):
                if any(item.voice_id == voice for item in provider.async_get_supported_voices(candidate) or []):
                    language = candidate
                    break
    voices = provider.async_get_supported_voices(language) or []
    return language, voice or (voices[0].voice_id if voices else None)


async def audio_for(hass, state, rule):
    from homeassistant.components.tts import generate_media_source_id, get_engine_instance

    speed = validate_speed(rule.get("speed", 1.0))
    if not hass.services.has_service("tts", "speak"):
        raise error("speech_engine_unavailable")
    try:
        provider = get_engine_instance(hass, rule.get("engine", ""))
    except KeyError:
        provider = None
    if provider is None:
        raise error("speech_engine_unavailable")
    language, voice = voice_settings(provider, rule.get("language"), rule.get("voice"))
    media_id = generate_media_source_id(
        hass, message_for(state, rule), engine=rule["engine"], cache=False,
        language=language,
        options={"voice": voice} if voice else None,
    )
    return replace(await resolve(hass, media_id, None), speed=speed)


async def preview(hass, playback, sensor, rule):
    sound = await audio_for(hass, hass.states.get(sensor), rule)
    return await playback.play(sound, Priority[rule["priority"].upper()], owner=f"speech:{sensor}")


class SensorSpeech:
    def __init__(self, hass, playback, options):
        self.hass, self.playback = hass, playback
        self.options = options
        self.rules = options.get(SPEECH_RULES, {})
        self._unsubscribe = None
        self._generation = 0
        self._closed = False
        self._last = {}
        self.last_result = {}
        self._lock = asyncio.Lock()

    def start(self):
        self._closed = False
        sensors = [sensor for sensor, rule in self.rules.items() if rule.get("trigger", "manual") != "manual"]
        if sensors:
            self._unsubscribe = async_track_state_change_event(self.hass, sensors, self._changed)

    def close(self):
        self._closed = True
        self._generation += 1
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    def update_options(self, options):
        self.close()
        self.options = options
        self.rules = options.get(SPEECH_RULES, {})
        self._last.clear()
        self.last_result.clear()
        self.start()

    async def say(self, sensor):
        rule = self.rules.get(sensor)
        if self._closed or rule is None:
            raise error("speech_rule_missing")
        if not rule.get("enabled", True):
            raise error("rule_disabled")
        generation = self._generation
        state = self.hass.states.get(sensor)
        sound = await audio_for(self.hass, state, effective_rule(self.hass, rule, self.options))
        if generation != self._generation:
            return False
        return await self.playback.play(sound, Priority[rule["priority"].upper()], owner=f"speech:{sensor}")

    def diagnostic(self, sensor):
        rule = self.rules.get(sensor, {})
        if not rule.get("enabled", True):
            return "Voz desactivada. La prueba manual sí puede sonar."
        if rule.get("trigger", "manual") == "manual":
            return "Solo manual: no habla al cambiar el sensor. Selecciona cuándo hablar."
        return self.last_result.get(sensor, "Automático preparado. Esperando un cambio que cumpla la condición.")

    def _current(self, sensor, expected):
        current = self.hass.states.get(sensor)
        # Attribute-only updates (battery, signal, etc.) must not cancel TTS.
        return current is not None and current.state == expected.state and current.last_changed == expected.last_changed

    async def _changed(self, event):
        sensor = event.data["entity_id"]
        new = event.data.get("new_state")
        old = event.data.get("old_state")
        async with self._lock:
            rule = self.rules.get(sensor)
            if self._closed or not rule or not rule.get("enabled", True):
                return
            if old is not None and new is not None and old.state == new.state:
                return
            if not matches(old, new, rule):
                self.last_result[sensor] = "Cambio omitido: estado no disponible o condición de voz no cumplida."
                return
            if not self._current(sensor, new):
                self.last_result[sensor] = "Cambio omitido: el sensor ya ha cambiado de nuevo."
                return
            now = time.monotonic()
            remaining = rule.get("cooldown", 60) - (now - self._last.get(sensor, -math.inf))
            if remaining > 0:
                self.last_result[sensor] = f"Cambio omitido por intervalo mínimo: quedaban {math.ceil(remaining)} segundos. No se pone en cola."
                return
            generation = self._generation
            self.last_result[sensor] = "Generando voz para el último cambio del sensor…"
            try:
                sound = await audio_for(self.hass, new, effective_rule(self.hass, rule, self.options))
                if generation != self._generation:
                    return
                if not self._current(sensor, new):
                    self.last_result[sensor] = "Voz descartada: el sensor cambió de estado mientras se generaba el audio."
                    return
                accepted = await self.playback.play(sound, Priority[rule["priority"].upper()], owner=f"speech:{sensor}")
                if accepted:
                    self._last[sensor] = time.monotonic()
                    self.last_result[sensor] = "Último aviso automático enviado al reproductor."
                else:
                    self.last_result[sensor] = "Voz bloqueada por un audio de mayor prioridad o una sirena protegida."
            except (HomeAssistantError, OSError, ValueError) as err:
                self.last_result[sensor] = "Error al generar o reproducir voz. Revisa el motor TTS y los registros de JackSignal."
                _LOGGER.warning("Sensor speech failed for %s (%s)", sensor, type(err).__name__)
