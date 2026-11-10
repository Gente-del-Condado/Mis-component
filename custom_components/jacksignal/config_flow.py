"""Native settings panel for Alarmo and sound assignments."""

from homeassistant.components import network
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

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
            step_id="init", menu_options=["alarm", "event", "sensor", "preview", "dlna"],
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
            if not user_input.get("sound"):
                rules.pop(self._key, None)
            else:
                try:
                    await self._validate_sound(user_input["sound"])
                except HomeAssistantError:
                    errors["sound"] = "local_sound_required"
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
        return self.async_show_form(
            step_id=step,
            data_schema=self.add_suggested_values_to_schema(validation.Schema(fields), user_input or current),
            errors=errors,
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
