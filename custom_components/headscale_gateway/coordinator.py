"""Consulta periódicamente la API REST existente del Gateway."""
from datetime import timedelta
import logging

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GatewayAuthError, GatewayError
from .const import DOMAIN


class GatewayCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(hass, logging.getLogger(__name__), config_entry=entry,
                         name=DOMAIN, update_interval=timedelta(seconds=30))
        self.client = client
        self.entry = entry

    async def _async_update_data(self):
        try:
            return await self.client.status()
        except GatewayAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GatewayError as err:
            raise UpdateFailed(str(err)) from err
