"""Alta por URL SSH, verificación de huella y clave de despliegue."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from . import DOMAIN
from .providers.forgejo import Forgejo, ForgejoError, generate_key, scan_host, ssh_address
from .providers.forgejo_releases import ReleaseError, Releases, validate_web_url


class ForgejoBackupConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ForgejoBackupOptions()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            url = user_input["url"].strip()
            try:
                host, port = ssh_address(url)
            except ForgejoError:
                errors["url"] = "invalid_url"
            else:
                await self.async_set_unique_id(f"{host}:{port}/{url.split('/', 3)[3]}")
                self._abort_if_unique_id_configured()
                try:
                    self._hosts = await self.hass.async_add_executor_job(scan_host, url)
                    self._private, self._public = await self.hass.async_add_executor_job(
                        generate_key
                    )
                except ForgejoError:
                    errors["base"] = "cannot_connect"
                else:
                    self._url = url
                    return await self.async_step_verify()
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema({vol.Required("url"): str}), errors=errors
        )

    async def async_step_verify(self, user_input=None):
        errors = {}
        if user_input:
            fingerprint = user_input["fingerprint"].strip()
            known_host = self._hosts.get(fingerprint)
            if not known_host:
                errors["fingerprint"] = "fingerprint_mismatch"
            else:
                provider = Forgejo(self._url, self._private, known_host)
                try:
                    await self.hass.async_add_executor_job(provider.check)
                except ForgejoError:
                    errors["base"] = "cannot_write"
                else:
                    return self.async_create_entry(
                        title="Forgejo · " + self._url.rsplit("/", 1)[-1].removesuffix(".git"),
                        data={
                            "url": self._url,
                            "identity": self._private,
                            "known_host": known_host,
                        },
                    )
        return self.async_show_form(
            step_id="verify",
            data_schema=vol.Schema({vol.Required("fingerprint"): str}),
            errors=errors,
            description_placeholders={
                "public_key": self._public,
                "fingerprint": ", ".join(self._hosts),
            },
        )


class ForgejoBackupOptions(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        options = self.config_entry.options
        if user_input is not None:
            web_url = user_input.get("web_url", "").strip()
            token = user_input.get("release_token", "").strip()
            if web_url == options.get("web_url"):
                token = token or options.get("release_token", "")
            if not web_url:
                return self.async_create_entry(data={})
            try:
                web_url = validate_web_url(web_url, self.config_entry.data["url"])
            except ReleaseError:
                errors["web_url"] = "invalid_web_url"
            else:
                if not token:
                    errors["release_token"] = "token_required"
                else:
                    try:
                        await self.hass.async_add_executor_job(Releases(web_url, token).check)
                    except ReleaseError:
                        errors["base"] = "release_access"
                    else:
                        return self.async_create_entry(
                            data={"web_url": web_url, "release_token": token}
                        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "web_url", description={"suggested_value": options.get("web_url", "")}
                    ): str,
                    vol.Optional("release_token"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )
