"""Alta, reconfiguración y reautenticación sin duplicar el contrato de conexión."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DOMAIN
from .connection import fetch_status, normalize_url


class PiVigiaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _step(self, step_id, user_input, entry=None):
        errors = {}
        defaults = entry.data if entry else {}
        if user_input is not None:
            try:
                url = normalize_url(user_input["url"])
                token = user_input.get("token", "").strip() or defaults.get("token", "")
                if len(token) < 16 or any(ord(c) < 32 for c in token):
                    raise PermissionError()
                await fetch_status(async_get_clientsession(self.hass), url, token)
            except PermissionError:
                errors["base"] = "invalid_auth"
            except (ValueError, TypeError):
                errors["base"] = "invalid_url"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                existing = await self.async_set_unique_id(url)
                if existing and (entry is None or existing.entry_id != entry.entry_id):
                    self._abort_if_unique_id_configured()
                if entry:
                    return self.async_update_reload_and_abort(
                        entry, unique_id=url, data_updates={"url": url, "token": token}
                    )
                return self.async_create_entry(title="PiVigia", data={"url": url, "token": token})
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({
                vol.Required("url", default=(user_input or defaults).get("url", "http://pivigia.local:8099")): str,
                (vol.Optional("token", default="") if entry else vol.Required("token")):
                    selector.TextSelector({"type": selector.TextSelectorType.PASSWORD}),
            }),
            errors=errors,
        )

    async def async_step_user(self, user_input=None):
        return await self._step("user", user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._step("reconfigure", user_input, self._get_reconfigure_entry())

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._step("reauth_confirm", user_input, self._get_reauth_entry())
