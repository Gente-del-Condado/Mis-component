"""Integración de estado: necesita el servicio PiVigia en ejecución."""

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

import logging

from .connection import fetch_status

DOMAIN = "pivigia"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    async def update():
        try:
            return await fetch_status(async_get_clientsession(hass), entry.data["url"], entry.data["token"])
        except PermissionError:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="invalid_auth") from None
        except Exception as error:
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="cannot_connect") from error

    coordinator = DataUpdateCoordinator(
        hass,
        logging.getLogger(__name__),
        name=DOMAIN,
        update_method=update,
        update_interval=timedelta(seconds=30),
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "binary_sensor"])
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, ["sensor", "binary_sensor"]):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False
