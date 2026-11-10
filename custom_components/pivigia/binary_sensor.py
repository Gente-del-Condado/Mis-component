"""Observaciones recientes: no representan presencia continua ni garantizan una alarma."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN

DETECTIONS = {"person": "mdi:account-alert", "car": "mdi:car",
              "animal": "mdi:paw", "motion": "mdi:motion-sensor"}
HEALTH = {"model_ready": "mdi:brain", "worker_alive": "mdi:cog"}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PiVigiaBinarySensor(coordinator, entry, key) for key in (*DETECTIONS, *HEALTH)])


class PiVigiaBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self.key = key
        icon = (DETECTIONS | HEALTH)[key]
        self._attr_unique_id = f"{entry.entry_id}_binary_{key}"
        self._attr_translation_key = key
        self._attr_icon = icon
        if key in HEALTH:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self):
        if self.key in HEALTH:
            value = self.coordinator.data.get(self.key)
        else:
            value = self.coordinator.data.get("detections", {}).get("categories", {}).get(self.key, {}).get("recent")
        return value if isinstance(value, bool) else None
