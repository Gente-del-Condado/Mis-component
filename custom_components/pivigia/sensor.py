"""Entidades de recuento y fecha: identificadores estables y nombres traducibles."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import datetime, timezone

from . import DOMAIN

STATES = ("sent", "queued", "filtered", "failed")


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PiVigiaSensor(coordinator, entry, key) for key in STATES])
    async_add_entities([PiVigiaDiagnosticSensor(coordinator, entry, key) for key in ("version", "model")])
    async_add_entities([PiVigiaDetectionTime(coordinator, entry, key)
                        for key in ("person", "car", "animal", "motion")])


class PiVigiaDetectionTime(CoordinatorEntity, SensorEntity):
    _attr_device_class = "timestamp"
    _attr_native_unit_of_measurement = None
    _attr_icon = "mdi:clock-outline"

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{entry.entry_id}_last_{key}"
        self._attr_translation_key = "last_" + key

    @property
    def native_value(self):
        value = self.coordinator.data.get("detections", {}).get("categories", {}).get(self.key, {}).get("last_seen")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                return datetime.fromtimestamp(value, timezone.utc)
            except (ValueError, OverflowError, OSError):
                pass
        return None


class PiVigiaDiagnosticSensor(CoordinatorEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = None

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_icon = "mdi:information-outline" if key == "version" else "mdi:brain"

    @property
    def native_value(self):
        return self.coordinator.data.get(self.key)


class PiVigiaSensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:email-search"

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key

    @property
    def native_value(self):
        if self.key == "queued":
            counts = self.coordinator.data.get("counts", {})
            return counts.get("queued", 0) + counts.get("processing", 0)
        return self.coordinator.data.get("counts", {}).get(self.key, 0)
