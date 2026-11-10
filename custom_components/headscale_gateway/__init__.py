"""Integración de solo lectura de Headscale Gateway para Home Assistant."""
from homeassistant.const import CONF_HOST, Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GatewayClient
from .const import CONF_TOKEN, CONF_VERIFY_SSL
from .coordinator import GatewayCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass, entry):
    client = GatewayClient(async_get_clientsession(hass), entry.data[CONF_HOST],
                           entry.data[CONF_TOKEN], entry.data.get(CONF_VERIFY_SSL, True))
    coordinator = GatewayCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
