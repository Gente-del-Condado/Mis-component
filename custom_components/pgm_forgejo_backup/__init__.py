"""Integración complementaria para las copias de Private Git Manager."""

from homeassistant.core import callback

DOMAIN = "pgm_forgejo_backup"
LISTENERS = DOMAIN + "_listeners"


async def async_setup_entry(hass, entry):
    from .backup import ForgejoBackupAgent

    entry.runtime_data = ForgejoBackupAgent(hass, entry)

    @callback
    def notify_agents():
        for listener in tuple(hass.data.get(LISTENERS, ())):
            listener()

    entry.async_on_unload(entry.async_on_state_change(notify_agents))
    entry.async_on_unload(entry.add_update_listener(_reload_options))
    return True


async def async_unload_entry(hass, entry):
    return True


async def _reload_options(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)
