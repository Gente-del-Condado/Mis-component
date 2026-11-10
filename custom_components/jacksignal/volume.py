"""Control the same PulseAudio output used by FFmpeg."""

from dataclasses import dataclass

import pulsectl


@dataclass(frozen=True)
class OutputVolume:
    level: float
    muted: bool


def output_volume(level: float | None = None, muted: bool | None = None) -> OutputVolume:
    """Run in an executor; each call owns its PulseAudio connection."""
    with pulsectl.Pulse("JackSignal volume", connect=False) as pulse:
        pulse.connect(timeout=3)
        sink = pulse.get_sink_by_name(pulse.server_info().default_sink_name)
        if level is not None:
            pulse.volume_set_all_chans(sink, level)
        if muted is not None:
            pulse.mute(sink, muted)
        sink = pulse.sink_info(sink.index)
        return OutputVolume(min(1.0, max(0.0, sink.volume.value_flat)), bool(sink.mute))
