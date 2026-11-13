"""Bounded, persistent diagnostic history shared by sensor audio and speech."""
from collections import deque
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_interval

DATA = "jacksignal_notice_history"


MANAGER = "jacksignal_history_manager"
STATUSES = {"preparing", "started", "completed", "interrupted", "omitted", "error"}


class Record(dict):
    """Keep the save callback outside the JSON payload."""
    changed = None

    def __deepcopy__(self, memo):
        return deepcopy(dict(self), memo)


def valid_days(days):
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
        raise ValueError("La retención debe ser un número entero entre 1 y 365 días.")
    return days


class HistoryStore:
    def __init__(self, hass):
        self.hass = hass
        self.store = Store(hass, 1, "jacksignal.history")
        self.days = 7
        self.cancel_timer = None

    def prune(self):
        cutoff = datetime.now(UTC) - timedelta(days=self.days)
        data = self.hass.data.setdefault(DATA, deque(maxlen=1000))
        keep = [item for item in data if datetime.fromisoformat(item["time"]) >= cutoff]
        if len(keep) != len(data):
            data.clear()
            data.extend(keep)
            return True
        return False

    def payload(self):
        self.prune()
        return {"days": self.days, "entries": [dict(item) for item in self.hass.data.get(DATA, ())]}

    def changed(self):
        self.store.async_delay_save(self.payload, 15)

    async def tick(self, _now):
        if self.prune():
            self.changed()

    def start(self):
        if self.cancel_timer is None:
            self.cancel_timer = async_track_time_interval(self.hass, self.tick, timedelta(hours=1))

    async def flush(self):
        await self.store.async_save(self.payload())


async def async_setup(hass):
    if manager := hass.data.get(MANAGER):
        manager.start()
        return
    manager = HistoryStore(hass)
    saved = await manager.store.async_load()
    data = hass.data.setdefault(DATA, deque(maxlen=1000))
    if saved is not None:
        if not isinstance(saved, dict) or not isinstance(saved.get("entries"), list):
            raise ValueError("El historial guardado no tiene un formato válido.")
        manager.days = valid_days(saved.get("days", 7))
        for item in saved["entries"][-1000:]:
            if not isinstance(item, dict) or not {"time", "sensor", "source", "priority", "status", "reason"} <= item.keys():
                continue
            if not all(isinstance(item[key], str) for key in ("sensor", "source", "priority", "status", "reason")):
                continue
            try:
                stamp = datetime.fromisoformat(item["time"])
                if stamp.tzinfo is None:
                    continue
            except (TypeError, ValueError):
                continue
            row = Record(item)
            if row["status"] in {"preparing", "started"}:
                row.update(status="interrupted", reason="Home Assistant se reinició antes de registrar el resultado final.", updated=datetime.now(UTC).isoformat())
            data.append(row)
    hass.data[MANAGER] = manager
    for row in data:
        if isinstance(row, Record):
            row.changed = manager.changed
    manager.prune()
    manager.start()
    manager.changed()


async def async_stop(hass):
    if manager := hass.data.get(MANAGER):
        if manager.cancel_timer:
            manager.cancel_timer()
            manager.cancel_timer = None
        await manager.flush()


def settings(hass):
    manager = hass.data.get(MANAGER)
    return {"days": manager.days if manager else 7, "maximum": 1000,
            "count": len(hass.data.get(DATA, ())), "persistent": manager is not None}


async def configure(hass, days):
    days = valid_days(days)
    manager = hass.data.get(MANAGER)
    if manager is None:
        raise ValueError("El almacenamiento del historial no está preparado. Recarga JackSignal.")
    manager.days = days
    await manager.flush()
    return settings(hass)


async def clear(hass, sensor=None):
    data = hass.data.setdefault(DATA, deque(maxlen=1000))
    retained = [item for item in data if sensor is not None and item["sensor"] != sensor]
    removed = len(data) - len(retained)
    data.clear()
    data.extend(retained)
    if manager := hass.data.get(MANAGER):
        await manager.flush()
    return removed


def query(hass, sensor, filters=None, limit=50):
    filters = {} if filters is None else filters
    if not isinstance(filters, dict) or filters.keys() - {"status", "kind", "priority", "days", "text"}:
        raise ValueError("Filtros de historial no válidos.")
    status, kind, priority = (filters.get(key, "all") for key in ("status", "kind", "priority"))
    days, text = filters.get("days", 0), filters.get("text", "")
    if not all(isinstance(value, str) for value in (status, kind, priority)) or status not in STATUSES | {"all"} or kind not in {"all", "voice", "audio"} or priority not in {"all", "low", "normal", "high", "critical"}:
        raise ValueError("Selecciona filtros de historial válidos.")
    if isinstance(days, bool) or not isinstance(days, int) or not 0 <= days <= 365 or not isinstance(text, str) or len(text) > 200:
        raise ValueError("Periodo o texto de búsqueda no válido.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("El límite debe estar entre 1 y 1000 registros.")
    if manager := hass.data.get(MANAGER):
        if manager.prune():
            manager.changed()
    cutoff = datetime.now(UTC) - timedelta(days=days) if days else None
    result = []
    for item in reversed(hass.data.get(DATA, ())):
        if item["sensor"] != sensor or status != "all" and item["status"] != status:
            continue
        voice = "voz" in item["source"].casefold()
        if kind == "voice" and not voice or kind == "audio" and voice:
            continue
        if priority != "all" and priority != item["priority"]:
            continue
        if cutoff and datetime.fromisoformat(item["time"]) < cutoff:
            continue
        if text.casefold() not in " ".join(str(item.get(key, "")) for key in ("source", "reason", "old", "new")).casefold():
            continue
        result.append(dict(item))
    return {"entries": deepcopy(result[:limit]), "total": len(result), "limit": limit}


def begin(hass, sensor, source, priority, old=None, new=None):
    entry = Record({"sensor": sensor, "source": source, "priority": priority,
             "time": datetime.now(UTC).isoformat(), "old": old, "new": new,
             "status": "preparing", "reason": "Preparando el aviso."})
    hass.data.setdefault(DATA, deque(maxlen=1000)).append(entry)
    if manager := hass.data.get(MANAGER):
        entry.changed = manager.changed
        manager.changed()
    return entry


def finish(entry, status, reason):
    if entry is not None:
        entry.update(status=status, reason=reason, updated=datetime.now(UTC).isoformat())
        if getattr(entry, "changed", None):
            entry.changed()


def playback_result(entry):
    def report(status):
        finish(entry, status, {"completed": "FFmpeg terminó sin errores; no confirma sonido físico.",
                              "interrupted": "Reproducción detenida o sustituida por otro audio.",
                              "error": "FFmpeg terminó con error. Revisa los registros de JackSignal."}[status])
    return report


def accepted(entry, result):
    finish(entry, "started" if result else "omitted",
           "Reproducción iniciada; pendiente de finalizar." if result else
           "El reproductor rechazó el aviso: prioridad superior, sirena protegida o reproductor cerrado.")


def entries(hass, sensor):
    return query(hass, sensor)["entries"]
