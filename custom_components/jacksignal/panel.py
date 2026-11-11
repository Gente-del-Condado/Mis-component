"""Administrator-only panel API for persistent alert rules and safe previews."""

import asyncio
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.exceptions import HomeAssistantError

from .alarm import CLOSED_STATES
from .const import ALARM, DEFAULT_PRIORITIES, DOMAIN, EVENTS, LOCAL_PREFIX, RULES, SENSOR_RULES, Priority
from .media import AUDIO_EXTENSIONS, resolve
from .selectors import validation as vol
from .speech import SPEECH_RULES, audio_for
from .playback import validate_speed

PANEL = "jacksignal"
DATA = "jacksignal_panel"
EVENT_NAMES = dict(zip(EVENTS, ("Alarma disparada", "Cuenta atrás de entrada", "Cuenta atrás de salida", "Alarma armada", "Alarma desarmada", "Fallo al armar")))
SECTIONS = {"alarm": RULES, "sensor": SENSOR_RULES, "speech": SPEECH_RULES}


def revision(options):
    return hashlib.sha256(json.dumps(dict(options), sort_keys=True, default=dict).encode()).hexdigest()


def rule_defaults(hass, kind, key):
    if kind == "alarm":
        return {"enabled": True, "priority": DEFAULT_PRIORITIES[key].name.lower(), "repeat": key == "triggered"}
    if kind == "speech":
        return {"enabled": True, "priority": "low", "before": "", "after": "", "unit": True, "trigger": "manual", "cooldown": 60, "speed": 1.0}
    from .config_flow import suggested_sensor_states
    opened, closed = suggested_sensor_states(hass.states.get(key))
    return {"enabled": True, "priority": "high", "open_state": opened, "closed_state": closed,
            "on_open": "never", "on_close": "never", "failed_to_arm": True}


def selected_rule(hass, entry, kind, key):
    if not isinstance(kind, str) or not isinstance(key, str) or kind not in SECTIONS:
        raise ValueError("Tipo de aviso no válido.")
    existing = entry.options.get(SECTIONS[kind], {}).get(key)
    if kind == "alarm":
        if key not in EVENTS:
            raise ValueError("Evento de Alarmo no válido.")
    elif existing is None:
        state = hass.states.get(key)
        domains = {"binary_sensor"} if kind == "sensor" else {"sensor", "binary_sensor"}
        if state is None or state.domain not in domains:
            raise ValueError("El sensor ya no está disponible. Actualiza la lista.")
    result = rule_defaults(hass, kind, key)
    result.update(deepcopy(existing or {}))
    if kind == "sensor" and existing:
        result["closed_state"] = existing.get("closed_state", CLOSED_STATES.get(result["open_state"], "off"))
    return result


def voice_info(hass, engine, language=None):
    from homeassistant.components.tts import get_engine_instance

    try:
        provider = get_engine_instance(hass, engine)
    except KeyError:
        provider = None
    if provider is None:
        raise ValueError("El motor de voz no está disponible. Configúralo en Home Assistant y actualiza la lista.")
    languages = list(provider.supported_languages or [])
    language = language or provider.default_language
    if language not in languages:
        raise ValueError("El motor no admite ese idioma. Selecciona uno de la lista.")
    voices = provider.async_get_supported_voices(language) or []
    return {"languages": languages, "default_language": provider.default_language,
            "language": language, "voices": [{"value": v.voice_id, "label": v.name} for v in voices]}


def playback_status(entry):
    player = entry.runtime_data
    sound = getattr(player, "sound", None)
    return {"active": sound is not None, "paused": bool(getattr(player, "paused", False)),
            "priority": getattr(player, "priority", Priority.LOW).name.lower(),
            "source": "Prueba del panel" if getattr(player, "owner", None) == "panel_preview" else "Aviso o reproducción externa"}


def snapshot(hass, entry):
    rows = []
    for kind, section in SECTIONS.items():
        rules = entry.options.get(section, {})
        if kind == "alarm":
            keys = list(EVENTS)
        else:
            domains = {"binary_sensor"} if kind == "sensor" else {"sensor", "binary_sensor"}
            keys = sorted({s.entity_id for s in hass.states.async_all() if s.domain in domains} | rules.keys())
        for key in keys:
            state = hass.states.get(key)
            rule = selected_rule(hass, entry, kind, key)
            configured = bool(rule.get("engine") if kind == "speech" else rule.get("sound") or rule.get("close_sound"))
            enabled = rule.get("enabled", True)
            rows.append({"kind": kind, "key": key, "name": EVENT_NAMES[key] if kind == "alarm" else state.name if state else key,
                         "state": state.state if state else None, "unit": state.attributes.get("unit_of_measurement", "") if state else "", "configured": configured,
                         "status": "unconfigured" if not configured else "configured" if enabled else "disabled",
                         "rule": rule})
    panel = entry.options.get(ALARM)
    return {"revision": revision(entry.options), "rows": rows, "playback": playback_status(entry), "alarm": panel,
            "alarm_available": bool(panel and hass.states.get(panel) and hass.states.get(panel).state not in {"unavailable", "unknown"}),
            "engines": [{"value": s.entity_id, "label": s.name} for s in hass.states.async_all("tts")]}


def local_media(directories):
    """Bound file listing and never traverse symlink directories."""
    items = []
    visited = 0
    for key, directory in directories.items():
        root = Path(directory).resolve()
        for base, dirs, files in root.walk(follow_symlinks=False):
            dirs[:] = sorted(name for name in dirs if not name.startswith("."))
            visited += 1
            if visited > 2000:
                return {"items": items, "truncated": True}
            for name in sorted(files):
                path = base / name
                if path.suffix.lower() not in AUDIO_EXTENSIONS or not path.resolve().is_relative_to(root):
                    continue
                relative = path.relative_to(root).as_posix()
                items.append({"value": f"{LOCAL_PREFIX}{key}/{relative}", "label": f"{key}/{relative}"})
                if len(items) >= 2000:
                    return {"items": items, "truncated": True}
    return {"items": items, "truncated": False}


async def validate_rule(hass, kind, key, supplied):
    if not isinstance(supplied, dict):
        raise ValueError("La configuración no es válida.")
    allowed = {"enabled", "priority"} | ({"sound", "repeat"} if kind == "alarm" else
        {"sound", "close_sound", "open_state", "closed_state", "on_open", "on_close", "failed_to_arm"} if kind == "sensor" else
        {"engine", "language", "voice", "speed", "before", "after", "unit", "trigger", "threshold", "cooldown"})
    if supplied.keys() - allowed:
        raise ValueError("Hay campos de configuración no reconocidos.")
    rule = {**rule_defaults(hass, kind, key), **deepcopy(supplied)}
    if rule.get("priority") not in {p.name.lower() for p in Priority}:
        raise ValueError("Selecciona una prioridad válida.")
    for field in ("enabled", "repeat", "failed_to_arm", "unit"):
        if field in rule and not isinstance(rule[field], bool):
            raise ValueError("El estado de activación no es válido.")
    if kind == "speech":
        rule["speed"] = validate_speed(rule.get("speed", 1.0))
        engine = rule.get("engine")
        if not isinstance(engine, str) or not engine.startswith("tts."):
            raise ValueError("Selecciona un motor de voz configurado en Home Assistant.")
        for field in ("language", "voice"):
            if field in rule and (not isinstance(rule[field], str) or len(rule[field]) > 200):
                raise ValueError("El idioma o la voz no son válidos.")
            if not rule.get(field):
                rule.pop(field, None)
        if rule.get("language") or rule.get("voice"):
            info = voice_info(hass, engine, rule.get("language"))
            if rule.get("voice") and rule["voice"] not in {v["value"] for v in info["voices"]}:
                raise ValueError("La voz no está disponible para ese idioma.")
        for field in ("before", "after"):
            if not isinstance(rule[field], str) or len(rule[field]) > 1000:
                raise ValueError("El texto de voz admite hasta 1000 caracteres por campo.")
        if rule["trigger"] not in {"manual", "change", "above", "below"}:
            raise ValueError("Selecciona cuándo debe hablar el sensor.")
        cooldown = rule["cooldown"]
        if isinstance(cooldown, bool) or not isinstance(cooldown, (float, int)) or not math.isfinite(cooldown) or not 0 <= cooldown <= 86400:
            raise ValueError("El intervalo debe estar entre 0 y 86400 segundos.")
        if rule["trigger"] in {"above", "below"}:
            threshold = rule.get("threshold")
            if isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not math.isfinite(threshold):
                raise ValueError("Escribe un umbral numérico válido.")
    else:
        for field in ("sound", "close_sound"):
            selection = rule.get(field)
            if not selection:
                rule.pop(field, None)
                continue
            if not isinstance(selection, dict) or not isinstance(selection.get("media_content_id"), str) or not selection["media_content_id"].startswith(LOCAL_PREFIX):
                raise ValueError("Selecciona un archivo de Mis medios.")
            await resolve(hass, selection["media_content_id"], None)
        if kind == "alarm" and not rule.get("sound"):
            raise ValueError("Selecciona el sonido del evento; para conservarlo sin avisar usa Desactivar.")
        if kind == "sensor":
            for field in ("open_state", "closed_state"):
                value = rule.get(field)
                if not isinstance(value, str) or not value.strip() or len(value) > 100 or value.strip().casefold() in {"unknown", "unavailable"}:
                    raise ValueError("Indica estados de apertura y cierre válidos.")
                rule[field] = value.strip().casefold()
            if rule["open_state"] == rule["closed_state"]:
                raise ValueError("Los estados de apertura y cierre deben ser distintos.")
            for mode, field in (("on_open", "sound"), ("on_close", "close_sound")):
                if rule[mode] not in {"never", "disarmed", "always"}:
                    raise ValueError("Selecciona una condición válida.")
                if rule[mode] != "never" and not rule.get(field):
                    raise ValueError("Cada aviso activado necesita su propio sonido de apertura o cierre.")
    return rule


async def handle(hass, entry, msg):
    """Shared action implementation; the websocket boundary requires an admin."""
    action = msg["action"]
    if action == "tts_info":
        return voice_info(hass, msg.get("engine", ""), msg.get("language"))
    if action == "status":
        return playback_status(entry)
    if action == "batch":
        if msg.get("revision") != revision(entry.options):
            raise ValueError("La configuración ha cambiado. Actualiza antes de guardar.")
        targets, changes = msg.get("targets"), msg.get("changes")
        if not isinstance(targets, list) or not 1 <= len(targets) <= 200:
            raise ValueError("Selecciona entre 1 y 200 avisos.")
        if not isinstance(changes, dict) or not changes or changes.keys() - {"enabled", "priority"}:
            raise ValueError("Solo puedes cambiar activación y prioridad en bloque.")
        options = deepcopy(dict(entry.options))
        for target in targets:
            if not isinstance(target, dict):
                raise ValueError("Selección de avisos no válida.")
            kind, key = target.get("kind"), target.get("key")
            rule = selected_rule(hass, entry, kind, key)
            if key not in entry.options.get(SECTIONS[kind], {}):
                raise ValueError("Configura todos los avisos seleccionados antes de modificarlos en bloque.")
            rule = await validate_rule(hass, kind, key, {**rule, **changes})
            options[SECTIONS[kind]][key] = rule
        if msg.get("revision") != revision(entry.options):
            raise ValueError("La configuración ha cambiado. Actualiza antes de guardar.")
        hass.config_entries.async_update_entry(entry, options=options)
        return {**snapshot(hass, entry), "message": f"Actualizados {len(targets)} avisos."}
    if action == "list":
        return snapshot(hass, entry)
    if action == "media":
        return await hass.async_add_executor_job(local_media, dict(hass.config.media_dirs))
    if action == "stop_test":
        await entry.runtime_data.stop(owner="panel_preview")
        return {"message": "Prueba detenida. Los avisos de Alarmo no se han detenido."}
    kind, key = msg.get("kind"), msg.get("key")
    rule = selected_rule(hass, entry, kind, key)
    if action == "test":
        if "rule" in msg:
            rule = await validate_rule(hass, kind, key, msg["rule"])
        if kind == "speech":
            sound = await audio_for(hass, hass.states.get(key), rule)
        else:
            field = msg.get("field", "sound")
            if field not in ({"sound", "close_sound"} if kind == "sensor" else {"sound"}):
                raise ValueError("Prueba no válida para este aviso.")
            if not rule.get(field):
                raise ValueError("Este aviso no tiene un sonido asignado.")
            sound = await resolve(hass, rule[field]["media_content_id"], None)
        # Tests never borrow a rule's critical priority, repeat, or Alarmo owner.
        accepted = await entry.runtime_data.play(sound, Priority.LOW, owner="panel_preview")
        return {"accepted": accepted, "message": "Prueba aceptada (P0, sin repetición)." if accepted else "No se ha reproducido: hay un aviso de mayor prioridad o una sirena protegida."}
    if action not in {"save", "toggle"}:
        raise ValueError("Acción no válida.")
    if msg.get("revision") != revision(entry.options):
        raise ValueError("La configuración ha cambiado en otra pantalla. Actualiza antes de guardar; tus cambios no se han aplicado.")
    if action == "save":
        rule = await validate_rule(hass, kind, key, msg.get("rule"))
    else:
        if key not in entry.options.get(SECTIONS[kind], {}):
            raise ValueError("Configura primero este aviso.")
        if not isinstance(msg.get("enabled"), bool):
            raise ValueError("Indica si quieres activar o desactivar el aviso.")
        rule["enabled"] = msg["enabled"]
    # Validate again after async resolution; other option screens may have saved meanwhile.
    if msg.get("revision") != revision(entry.options):
        raise ValueError("La configuración ha cambiado. Actualiza antes de guardar.")
    options = deepcopy(dict(entry.options))
    options.setdefault(SECTIONS[kind], {})[key] = rule
    hass.config_entries.async_update_entry(entry, options=options)
    return snapshot(hass, entry)


@websocket_api.websocket_command({vol.Required("type"): "jacksignal/manage", vol.Required("action"): str,
    vol.Optional("kind"): str, vol.Optional("key"): str, vol.Optional("revision"): str,
    vol.Optional("rule"): dict, vol.Optional("enabled"): bool, vol.Optional("field"): str,
    vol.Optional("engine"): str, vol.Optional("language"): str,
    vol.Optional("targets"): [dict], vol.Optional("changes"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_manage(hass, connection, msg):
    current = hass.data.get(DATA)
    if not current or not current.get("entry"):
        connection.send_error(msg["id"], "not_loaded", "JackSignal no está cargado. Revisa la integración.")
        return
    try:
        async with current["lock"]:
            result = await handle(hass, current["entry"], msg)
        connection.send_result(msg["id"], result)
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_request", str(err))
    except (HomeAssistantError, OSError):
        connection.send_error(msg["id"], "audio_error", "No se pudo preparar el audio. Comprueba el archivo, el motor de voz y los registros de JackSignal.")


async def async_setup_panel(hass, entry):
    current = hass.data.setdefault(DATA, {"lock": asyncio.Lock()})
    if not current.get("registered"):
        await hass.http.async_register_static_paths([
            StaticPathConfig("/jacksignal-panel.js", str(Path(__file__).with_name("panel.js")), False)
        ])
        websocket_api.async_register_command(hass, ws_manage)
        current["registered"] = True
    current["entry"] = entry
    # Versioned module URLs prevent a previous panel remaining cached after upgrades.
    manifest = await hass.async_add_executor_job(Path(__file__).with_name("manifest.json").read_text)
    version = json.loads(manifest)["version"]
    await panel_custom.async_register_panel(hass, frontend_url_path=PANEL,
        webcomponent_name="jacksignal-panel", sidebar_title="JackSignal", sidebar_icon="mdi:bullhorn-outline",
        module_url=f"/jacksignal-panel.js?v={version}", require_admin=True)

    def unload():
        current.pop("entry", None)
        frontend.async_remove_panel(hass, PANEL)
    entry.async_on_unload(unload)
