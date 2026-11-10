"""Indicadores de red y configuración del Gateway."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import GatewayEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(GatewayBinarySensor(entry.runtime_data, key) for key in
                       ('vpn_connected', 'lan_https_active', 'setup_required'))


class GatewayBinarySensor(GatewayEntity, BinarySensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self._attr_device_class = (BinarySensorDeviceClass.PROBLEM if key == 'setup_required'
                                   else BinarySensorDeviceClass.CONNECTIVITY)

    @property
    def is_on(self):
        return self.coordinator.data.get(self.key)
