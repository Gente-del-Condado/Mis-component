"""Own the FFmpeg process and serialize playback transitions."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
import signal
from typing import Any

from .const import Priority

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Sound:
    """A resolved audio input."""

    source: str
    title: str
    local: bool


class Playback:
    """Use one process for the physical output."""

    def __init__(self, create_task: Callable[..., asyncio.Task[Any]]) -> None:
        self._create_task = create_task
        self._lock = asyncio.Lock()
        self._process: asyncio.subprocess.Process | None = None
        self._closed = False
        self.paused = False
        self.sound: Sound | None = None
        self.priority = Priority.LOW
        self.owner: str | None = None
        self._repeating_siren = False
        self.changed: Callable[[], None] = lambda: None
        self.listeners: set[Callable[[], None]] = set()

    def notify(self) -> None:
        self.changed()
        for listener in tuple(self.listeners):
            listener()

    async def play(
        self,
        sound: Sound,
        priority: Priority,
        *,
        repeat: bool = False,
        owner: str | None = None,
    ) -> bool:
        """Replace active playback when the new priority permits it."""
        async with self._lock:
            if self._closed:
                return False
            if self._process and self._process.returncode is None:
                if self._repeating_siren or priority < self.priority:
                    _LOGGER.debug(
                        "Audio rejected: owner=%s priority=%s; active owner=%s priority=%s siren=%s",
                        owner, priority.name, self.owner, self.priority.name, self._repeating_siren,
                    )
                    return False
            await self._stop()
            protocols = "file" if sound.local else "http,https,tcp,tls,crypto"
            input_options = ["-protocol_whitelist", protocols]
            if repeat:
                input_options += ["-stream_loop", "-1"]
            try:
                process = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                    *input_options, "-i", sound.source,
                    "-map", "0:a:0", "-vn",
                    # The PulseAudio muxer disconnects without draining its buffer.
                    # A bounded buffer and trailing silence keep the audible tail
                    # alive until it reaches the sink. Infinite loops do not reach
                    # EOF, so apad does not insert gaps between siren iterations.
                    "-af", "apad=pad_dur=1", "-f", "pulse", "-buffer_duration", "200",
                    "-name", "JackSignal", "default",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError:
                self.notify()
                raise
            _LOGGER.debug("Audio started: owner=%s priority=%s repeat=%s", owner, priority.name, repeat)
            self._process = process
            self.sound = sound
            self.priority = priority
            self.owner = owner
            self._repeating_siren = repeat and owner == "triggered" and priority == Priority.CRITICAL
            self.notify()
            self._create_task(self._watch(process, sound), "jacksignal playback")

            return True

    async def _watch(self, process: asyncio.subprocess.Process, sound: Sound) -> None:
        # Drain stderr while the process runs so an error cannot block playback.
        error = b""
        assert process.stderr is not None
        while chunk := await process.stderr.read(4096):
            error = (error + chunk)[-4096:]
        await process.wait()
        async with self._lock:
            if self._process is not process:
                return
            _LOGGER.debug("Audio finished: owner=%s exit=%s", self.owner, process.returncode)
            self._reset()
            self.notify()
            if process.returncode:
                # Only local diagnostics are safe to include verbatim.
                details = error.decode(errors="replace").strip() if sound.local else ""
                _LOGGER.error(
                    "FFmpeg failed playing %s (exit %s)%s",
                    sound.title, process.returncode, f": {details}" if details else "",
                )

    async def set_paused(self, paused: bool, *, owner: str | None = None) -> None:
        """Pause or resume the existing process."""
        async with self._lock:
            if owner is not None and owner != self.owner:
                return
            process = self._process
            if process is None or process.returncode is not None or self.paused == paused:
                return
            try:
                process.send_signal(signal.SIGSTOP if paused else signal.SIGCONT)
            except ProcessLookupError:
                return
            self.paused = paused
            self.notify()

    async def stop(self, *, owner: str | None = None) -> None:
        """Stop playback, optionally only if started by the given owner."""
        async with self._lock:
            if owner is None or owner == self.owner:
                await self._stop()
                self.notify()

    async def close(self) -> None:
        """Release the audio output and reject future requests."""
        async with self._lock:
            self._closed = True
            await self._stop()

    async def _stop(self) -> None:
        if (process := self._process) is not None:
            if process.returncode is None:
                _LOGGER.debug("Audio interrupted: owner=%s priority=%s", self.owner, self.priority.name)
                try:
                    # Also works when the process is paused with SIGSTOP.
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()
        self._reset()

    def _reset(self) -> None:
        self._process = None
        self.sound = None
        self.paused = False
        self.priority = Priority.LOW
        self.owner = None
        self._repeating_siren = False
