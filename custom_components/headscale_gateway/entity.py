"""Metadatos comunes del dispositivo Gateway."""
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class GatewayEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = coordinator.entry.entry_id + '_' + key
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name='Headscale Gateway', manufacturer='Headscale Gateway',
            model='Private HTTPS Gateway', sw_version=coordinator.data.get('version'),
        )
