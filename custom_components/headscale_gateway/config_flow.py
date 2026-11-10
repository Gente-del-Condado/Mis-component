"""Configura, reconfigura y renueva un token delegado próximo a caducar."""
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import GatewayAuthError, GatewayClient, GatewayError, normalize_url
from .const import CONF_TOKEN, CONF_VERIFY_SSL, DOMAIN


class GatewayConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, user_input):
        values = dict(user_input)
        values[CONF_HOST] = normalize_url(values[CONF_HOST])
        client = GatewayClient(async_get_clientsession(self.hass), values[CONF_HOST],
                               values[CONF_TOKEN], values.get(CONF_VERIFY_SSL, True))
        await client.status()
        return values

    async def _form(self, step, user_input=None, entry=None):
        errors = {}
        if user_input is not None:
            try:
                values = await self._validate(user_input)
                if entry is not None:
                    # La URL identifica la instancia; evita reemplazar otra entrada.
                    await self.async_set_unique_id(values[CONF_HOST])
                    if values[CONF_HOST] != entry.unique_id:
                        self._abort_if_unique_id_configured()
                    self.hass.config_entries.async_update_entry(entry, unique_id=values[CONF_HOST])
                    return self.async_update_reload_and_abort(entry, data_updates=values)
                await self.async_set_unique_id(values[CONF_HOST])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title='Headscale Gateway', data=values)
            except GatewayAuthError:
                errors['base'] = 'invalid_auth'
            except GatewayError:
                errors['base'] = 'cannot_connect'
        defaults = user_input or (entry.data if entry else {})
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, '')): str,
            vol.Required(CONF_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Required(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, True)): bool,
        })
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)

    async def async_step_user(self, user_input=None):
        return await self._form('user', user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._form('reconfigure', user_input, self._get_reconfigure_entry())

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._form('reauth_confirm', user_input, self._get_reauth_entry())
