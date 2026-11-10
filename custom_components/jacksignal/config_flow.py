"""Native settings panel for Alarmo and sound assignments."""

import math
import re
from urllib.parse import unquote

from homeassistant.components import network
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

from .alarm import CLOSED_STATES
from .const import (
    ALARM,
    DEFAULT_PRIORITIES,
    DOMAIN,
    EVENTS,
    LOCAL_PREFIX,
    RULES,
    SENSOR_RULES,
    Priority,
)
from .dlna import DLNA, settings
from .media import resolve
from .selectors import media_selector, priority_selector, validation
from .speech import SPEECH_RULES, preview


class SonidosConfigFlow(ConfigFlow, domain=DOMAIN):
    """Install one player for this Home Assistant instance."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="JackSignal", data={})
        return self.async_show_form(step_id="user", data_schema=validation.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SoundOptions()


class SoundOptions(OptionsFlow):
    """Use native configuration dialogs for sound rules."""

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init", menu_options=["overview", "alarm", "event", "sensor", "speech", "preview", "dlna"],
        )

    async def async_step_speech(self, user_input=None):
        if user_input is not None:
            self._key = user_input["sensor"]
            return await self.async_step_speech_rule()
        return self.async_show_form(step_id="speech", data_schema=validation.Schema({
            validation.Required("sensor"): selector.EntitySelector({"domain": ["sensor", "binary_sensor"]}),
        }))

    async def async_step_speech_rule(self, user_input=None):
        options = dict(self.config_entry.options)
        rules = dict(options.get(SPEECH_RULES, {}))
        current = rules.get(self._key, {})
        errors, status = {}, ""
        if user_input is not None:
            rule = {key: value for key, value in user_input.items() if key != "operation"}
            operation = user_input.get("operation", "save")
            if operation == "delete":
                rules.pop(self._key, None)
            else:
                if rule.get("trigger") in {"above", "below"} and (
                    rule.get("threshold") is None or not math.isfinite(float(rule["threshold"]))
                ):
                    errors["threshold"] = "speech_threshold"
                if not rule.get("engine"):
                    errors["engine"] = "speech_engine"
                if operation == "preview" and not errors:
                    try:
                        accepted = await preview(self.hass, self.config_entry.runtime_data, self._key, rule)
                        if not accepted:
                            errors["base"] = "higher_priority"
                        else:
                            status = "✓"
                    except (HomeAssistantError, OSError, ValueError):
                        errors["base"] = "speech_failed"
                if not errors and operation == "save":
                    rules[self._key] = rule
            if not errors and operation in {"save", "delete"}:
                options[SPEECH_RULES] = rules
                return self.async_create_entry(data=options)
        schema = validation.Schema({
            validation.Optional("engine"): selector.EntitySelector({"domain": "tts"}),
            validation.Optional("before", default=""): selector.TextSelector(),
            validation.Optional("after", default=""): selector.TextSelector(),
            validation.Required("unit", default=True): selector.BooleanSelector(),
            validation.Required("trigger", default="manual"): selector.SelectSelector({
                "options": ["manual", "change", "above", "below"], "translation_key": "speech_trigger",
                "mode": selector.SelectSelectorMode.DROPDOWN,
            }),
            validation.Optional("threshold"): selector.NumberSelector({"mode": "box", "step": "any"}),
            validation.Required("cooldown", default=60): selector.NumberSelector({"min": 0, "max": 86400, "step": 1, "mode": "box"}),
            validation.Required("priority", default="low"): priority_selector(),
            validation.Required("operation", default="save"): selector.SelectSelector({
                "options": ["save", "preview", "delete"], "translation_key": "speech_operation",
                "mode": selector.SelectSelectorMode.DROPDOWN,
            }),
        })
        return self.async_show_form(step_id="speech_rule", data_schema=self.add_suggested_values_to_schema(
            schema, user_input if user_input is not None else current,
        ), errors=errors, description_placeholders={"sensor": self._key, "status": status})

    async def async_step_overview(self, user_input=None):
        """Show saved assignments without changing them or playing any audio."""
        options = self.config_entry.options
        translations = await async_get_translations(
            self.hass, self.hass.config.language, "selector", {DOMAIN},
        )

        def translated(group, value):
            return translations.get(f"component.{DOMAIN}.selector.{group}.options.{value}", value)

        def plain(value):
            return re.sub(r"([\\`*_{}\[\]()<>#!|])", r"\\\1", str(value).replace("\n", " "))

        def sound(rule):
            if not rule or not rule.get("sound"):
                return "—"
            media = rule["sound"]["media_content_id"]
            label = unquote(media.removeprefix(LOCAL_PREFIX))
            priority = Priority[rule["priority"].upper()].value
            repeat = " ↻" if rule.get("repeat") else ""
            return f"{plain(label)} · P{priority}{repeat}"

        panel_id = options.get(ALARM)
        panel = self.hass.states.get(panel_id) if panel_id else None
        values = {kind: sound(options.get(RULES, {}).get(kind)) for kind in EVENTS}
        values["alarm"] = plain(f"{panel.name} ({panel_id})" if panel else panel_id or "—")
        sensor_rules = options.get(SENSOR_RULES, {})
        sensors = {state.entity_id: state for state in self.hass.states.async_all("binary_sensor")
                   if state.attributes.get("device_class") in {"door", "window", "opening", "garage_door"}
                   or state.entity_id in sensor_rules}
        lines = []
        for entity_id in sorted(sensors.keys() | sensor_rules.keys()):
            state = sensors.get(entity_id)
            name = f"{state.name} ({entity_id})" if state else entity_id
            rule = sensor_rules.get(entity_id)
            conditions = []
            if rule:
                conditions.append(translated("open_state", rule.get("open_state", "on")))
                if rule.get("sound") and rule.get("failed_to_arm", True):
                    conditions.append(translated("sensor_summary", "failed_to_arm"))
                mode = rule.get("on_open", "never")
                if rule.get("sound") and mode != "never":
                    conditions.append(translated("on_open", mode))
                if not conditions and not rule.get("close_sound"):
                    conditions.append(translated("sensor_summary", "disabled"))
            suffix = f" · {plain(', '.join(conditions))}" if conditions else ""
            lines.append(f"- {plain(name)}: {sound(rule)}{suffix}")
            if rule and rule.get("close_sound"):
                close_label = translated("sensor_summary", "close")
                close_mode = translated("on_close", rule.get("on_close", "never"))
                close_audio = sound({**rule, "sound": rule["close_sound"]})
                lines.append(f"  - {plain(close_label)}: {close_audio} · {plain(close_mode)}")
        values["sensors"] = "\n".join(lines) or "—"
        values["speech"] = "\n".join(
            f"- {plain(sensor)}: {plain(rule.get('before', ''))} … {plain(rule.get('after', ''))}"
            f" · {plain(rule['engine'])} · P{Priority[rule['priority'].upper()].value}"
            f" · {plain(translated('speech_trigger', rule.get('trigger', 'manual')))}"
            for sensor, rule in sorted(options.get(SPEECH_RULES, {}).items())
        ) or "—"
        return self.async_show_menu(
            step_id="overview", menu_options=["event", "sensor", "speech", "alarm", "init"],
            description_placeholders=values,
        )

    async def async_step_dlna(self, user_input=None):
        options = dict(self.config_entry.options)
        errors = {}
        if user_input is not None:
            try:
                settings(user_input)
                receiver = self.hass.data.get(DOMAIN)
                if receiver is not None:
                    await receiver.configure({**options, DLNA: user_input})
            except (ValueError, KeyError):
                errors["base"] = "dlna_address"
            except OSError:
                errors["base"] = "dlna_start"
            else:
                options[DLNA] = user_input
                return self.async_create_entry(data=options)
        addresses = {}
        for adapter in await network.async_get_adapters(self.hass):
            for ipv4 in adapter["ipv4"]:
                address = ipv4["address"]
                try:
                    settings({"enabled": True, "address": address})
                except ValueError:
                    continue
                addresses[address] = f"{adapter['name']} — {address}"
        schema = validation.Schema({
            validation.Required("enabled", default=False): selector.BooleanSelector(),
            validation.Optional("address"): selector.SelectSelector({
                "options": [{"value": ip, "label": label} for ip, label in addresses.items()],
                "custom_value": True,
                "mode": selector.SelectSelectorMode.DROPDOWN,
            }),
            validation.Required("port", default=49200): selector.NumberSelector({
                "min": 1024, "max": 65535, "step": 1, "mode": "box",
            }),
            validation.Required("discovery", default=True): selector.BooleanSelector(),
        })
        return self.async_show_form(
            step_id="dlna", data_schema=self.add_suggested_values_to_schema(
                schema, user_input if user_input is not None else options.get(DLNA, {}),
            ), errors=errors,
        )

    async def async_step_alarm(self, user_input=None):
        options = dict(self.config_entry.options)
        if user_input is not None:
            options.pop(ALARM, None)
            options.update(user_input)
            return self.async_create_entry(data=options)
        schema = validation.Schema({
            validation.Optional(ALARM): selector.EntitySelector({"domain": "alarm_control_panel"}),
        })
        return self.async_show_form(
            step_id="alarm", data_schema=self.add_suggested_values_to_schema(schema, options),
        )

    async def async_step_event(self, user_input=None):
        if user_input is not None:
            self._key = user_input["event"]
            return await self.async_step_event_sound()
        return self.async_show_form(
            step_id="event",
            data_schema=validation.Schema({
                validation.Required("event"): selector.SelectSelector({
                    "options": list(EVENTS), "translation_key": "alarm_event",
                    "mode": selector.SelectSelectorMode.DROPDOWN,
                }),
            }),
        )

    async def async_step_sensor(self, user_input=None):
        if user_input is not None:
            self._key = user_input["sensor"]
            return await self.async_step_sensor_sound()
        return self.async_show_form(
            step_id="sensor",
            data_schema=validation.Schema({
                validation.Required("sensor"): selector.EntitySelector({"domain": "binary_sensor"}),
            }),
        )

    async def async_step_event_sound(self, user_input=None):
        return await self._edit_rule(
            "event_sound", RULES, DEFAULT_PRIORITIES[self._key], user_input,
        )

    async def async_step_sensor_sound(self, user_input=None):
        return await self._edit_rule("sensor_sound", SENSOR_RULES, Priority.HIGH, user_input)

    async def _edit_rule(self, step, section, default_priority, user_input):
        options = dict(self.config_entry.options)
        rules = dict(options.get(section, {}))
        current = rules.get(self._key, {})
        errors = {}
        if user_input is not None:
            if not user_input.get("sound") and not (section == SENSOR_RULES and user_input.get("close_sound")):
                rules.pop(self._key, None)
            else:
                try:
                    for field in ("sound", "close_sound") if section == SENSOR_RULES else ("sound",):
                        if user_input.get(field):
                            await self._validate_sound(user_input[field])
                except HomeAssistantError:
                    errors[field] = "local_sound_required"
                else:
                    rules[self._key] = user_input
            if not errors:
                options[section] = rules
                return self.async_create_entry(data=options)

        fields = {
            validation.Optional("sound"): media_selector(),
            validation.Required("priority", default=default_priority.name.lower()): priority_selector(),
        }
        if section == RULES and self._key == "triggered":
            fields[validation.Optional("repeat", default=True)] = selector.BooleanSelector()
        if section == SENSOR_RULES:
            fields[validation.Required("open_state", default=current.get("open_state", "on"))] = selector.SelectSelector({
                "options": list(CLOSED_STATES), "translation_key": "open_state",
                "mode": selector.SelectSelectorMode.DROPDOWN,
            })
            fields[validation.Optional("close_sound")] = media_selector()
            fields[validation.Required("on_close", default="never")] = selector.SelectSelector({
                "options": ["never", "disarmed", "always"], "translation_key": "on_close",
                "mode": selector.SelectSelectorMode.DROPDOWN,
            })
            fields[validation.Required("failed_to_arm", default=True)] = selector.BooleanSelector()
            fields[validation.Required("on_open", default="never")] = selector.SelectSelector({
                "options": ["never", "disarmed", "always"], "translation_key": "on_open",
                "mode": selector.SelectSelectorMode.DROPDOWN,
            })
        return self.async_show_form(
            step_id=step,
            data_schema=self.add_suggested_values_to_schema(validation.Schema(fields), user_input or current),
            errors=errors,
            description_placeholders={"sensor": self._key, "state": (
                self.hass.states.get(self._key).state if self.hass.states.get(self._key) else "unavailable"
            )} if section == SENSOR_RULES else None,
        )

    async def async_step_preview(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                sound = await self._validate_sound(user_input["sound"])
                playback = getattr(self.config_entry, "runtime_data", None)
                if playback is None:
                    errors["base"] = "ffmpeg_unavailable"
                elif not await playback.play(sound, Priority.LOW):
                    errors["base"] = "higher_priority"
            except HomeAssistantError:
                errors["sound"] = "local_sound_required"
            except OSError:
                errors["base"] = "ffmpeg_unavailable"
        return self.async_show_form(
            step_id="preview",
            data_schema=self.add_suggested_values_to_schema(
                validation.Schema({validation.Required("sound"): media_selector()}), user_input or {},
            ),
            errors=errors,
            description_placeholders={
                "status": "✓" if user_input is not None and not errors else "",
            },
        )

    async def _validate_sound(self, selection):
        media_id = selection["media_content_id"]
        if not media_id.startswith(LOCAL_PREFIX):
            raise HomeAssistantError("Expected local audio")
        return await resolve(self.hass, media_id, None)
