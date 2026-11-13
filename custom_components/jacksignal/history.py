"""Bounded, in-memory diagnostic history shared by sensor audio and speech."""
from collections import deque
from copy import deepcopy
from datetime import UTC, datetime

DATA = "jacksignal_notice_history"


def begin(hass, sensor, source, priority, old=None, new=None):
    entry = {"sensor": sensor, "source": source, "priority": priority,
             "time": datetime.now(UTC).isoformat(), "old": old, "new": new,
             "status": "preparing", "reason": "Preparando el aviso."}
    hass.data.setdefault(DATA, deque(maxlen=1000)).append(entry)
    return entry


def finish(entry, status, reason):
    if entry is not None:
        entry.update(status=status, reason=reason, updated=datetime.now(UTC).isoformat())


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
    return deepcopy([item for item in reversed(hass.data.get(DATA, ())) if item["sensor"] == sensor][:50])
