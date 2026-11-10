"""Audio-only UPnP MediaRenderer services."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import ClassVar

import pulsectl
from async_upnp_client.const import ServiceInfo
from async_upnp_client.exceptions import UpnpError
from async_upnp_client.server import (
    UpnpServerService,
    callable_action,
    create_event_var,
    create_state_var,
)

from .const import Priority
from .dlna_media import audio_source, fault
from .volume import output_volume

PROTOCOLS = ",".join(
    f"http-get:*:{mime}:*"
    for mime in (
        "audio/mpeg",
        "audio/flac",
        "audio/x-flac",
        "audio/wav",
        "audio/x-wav",
        "audio/aac",
        "audio/mp4",
        "audio/ogg",
        "audio/opus",
    )
)


def definition(name):
    return ServiceInfo(
        f"urn:upnp-org:serviceId:{name}",
        f"urn:schemas-upnp-org:service:{name}:1",
        f"/{name}/control",
        f"/{name}/event",
        f"/{name}.xml",
        ET.Element("service"),
    )


def instance(value):
    if value != 0:
        raise fault(718, "Invalid InstanceID")


class AudioService(UpnpServerService):
    async def async_send_events(self, subscriber=None):
        try:
            await super().async_send_events(subscriber)
        except (UpnpError, OSError, TimeoutError):
            logging.getLogger(__name__).debug("DLNA controller is no longer reachable")


class Transport(AudioService):
    SERVICE_DEFINITION = definition("AVTransport")
    STATE_VARIABLE_DEFINITIONS: ClassVar[dict] = {
        "A_ARG_TYPE_InstanceID": create_state_var("ui4"),
        "AVTransportURI": create_state_var("string", default=""),
        "AVTransportURIMetaData": create_state_var("string", default=""),
        "TransportState": create_state_var("string", default="NO_MEDIA_PRESENT"),
        "TransportStatus": create_state_var("string", default="OK"),
        "TransportPlaySpeed": create_state_var("string", default="1", allowed=["1"]),
        "NumberOfTracks": create_state_var("ui4", default="0"),
        "CurrentMediaDuration": create_state_var("string", default="00:00:00"),
        "PlaybackStorageMedium": create_state_var("string", default="NETWORK"),
        "RecordStorageMedium": create_state_var("string", default="NOT_IMPLEMENTED"),
        "RecordMediumWriteStatus": create_state_var(
            "string", default="NOT_IMPLEMENTED"
        ),
        "CurrentTrack": create_state_var("ui4", default="0"),
        "CurrentTrackDuration": create_state_var("string", default="00:00:00"),
        "RelativeTimePosition": create_state_var("string", default="NOT_IMPLEMENTED"),
        "AbsoluteTimePosition": create_state_var("string", default="NOT_IMPLEMENTED"),
        "RelativeCounterPosition": create_state_var("i4", default="2147483647"),
        "AbsoluteCounterPosition": create_state_var("i4", default="2147483647"),
        "CurrentTransportActions": create_state_var("string", default=""),
        "CurrentPlayMode": create_state_var("string", default="NORMAL"),
        "CurrentRecordQualityMode": create_state_var(
            "string", default="NOT_IMPLEMENTED"
        ),
        "PossiblePlaybackStorageMedia": create_state_var("string", default="NETWORK"),
        "PossibleRecordStorageMedia": create_state_var(
            "string", default="NOT_IMPLEMENTED"
        ),
        "PossibleRecordQualityModes": create_state_var(
            "string", default="NOT_IMPLEMENTED"
        ),
        "LastChange": create_event_var("string"),
    }

    def __init__(self, requester):
        self.backend = None
        self.loaded = None
        self.metadata = ""
        self._was_active = False
        self._lock = asyncio.Lock()
        super().__init__(requester)

    def available(self):
        if self.backend.sound and (
            self.backend.priority > Priority.LOW
            or self.backend.owner not in {None, "dlna"}
        ):
            raise fault(701, "Higher priority audio is active")

    def state(self):
        if self.backend.owner == "dlna" and self.backend.sound:
            return "PAUSED_PLAYBACK" if self.backend.paused else "PLAYING"
        return "STOPPED" if self.loaded else "NO_MEDIA_PRESENT"

    def publish(self):
        if self._was_active and self.backend.owner != "dlna":
            self.loaded = None
            self.metadata = ""
        self._was_active = self.backend.owner == "dlna"
        root = ET.Element("Event", xmlns="urn:schemas-upnp-org:metadata-1-0/AVT/")
        item = ET.SubElement(root, "InstanceID", val="0")
        for key, value in {
            "TransportState": self.state(),
            "TransportStatus": "OK",
            "AVTransportURI": self.loaded.source if self.loaded else "",
            "AVTransportURIMetaData": self.metadata,
            "CurrentTrackURI": self.loaded.source if self.loaded else "",
            "CurrentTransportActions": self.actions_available(),
        }.items():
            ET.SubElement(item, key, val=value)
        self.state_variable("LastChange").value = ET.tostring(root, encoding="unicode")

    def actions_available(self):
        return (
            "Play,Stop,Pause"
            if self.state() == "PLAYING"
            else "Play,Stop"
            if self.loaded
            else ""
        )

    @callable_action(
        "SetAVTransportURI",
        {
            "InstanceID": "A_ARG_TYPE_InstanceID",
            "CurrentURI": "AVTransportURI",
            "CurrentURIMetaData": "AVTransportURIMetaData",
        },
        {},
    )
    async def set_uri(self, InstanceID: int, CurrentURI: str, CurrentURIMetaData: str):
        instance(InstanceID)
        async with self._lock:
            self.available()
            try:
                sound = await audio_source(CurrentURI, CurrentURIMetaData)
            except OSError as err:
                raise fault(501, "Audio inspection unavailable") from err
            self.available()
            was_playing = self.state() == "PLAYING"
            await self.backend.stop(owner="dlna")
            self.loaded, self.metadata = sound, CurrentURIMetaData
            if was_playing and not await self.backend.play(
                sound, Priority.LOW, owner="dlna"
            ):
                raise fault(701, "Higher priority audio is active")
            self.publish()
        return {}

    @callable_action(
        "Play",
        {"InstanceID": "A_ARG_TYPE_InstanceID", "Speed": "TransportPlaySpeed"},
        {},
    )
    async def play(self, InstanceID: int, Speed: str):
        instance(InstanceID)
        async with self._lock:
            self.available()
            if not self.loaded:
                raise fault(716, "No audio selected")
            if self.backend.owner == "dlna" and self.backend.sound == self.loaded:
                await self.backend.set_paused(False, owner="dlna")
            elif not await self.backend.play(self.loaded, Priority.LOW, owner="dlna"):
                raise fault(701, "Higher priority audio is active")
        return {}

    @callable_action("Pause", {"InstanceID": "A_ARG_TYPE_InstanceID"}, {})
    async def pause(self, InstanceID: int):
        instance(InstanceID)
        self.available()
        await self.backend.set_paused(True, owner="dlna")
        return {}

    @callable_action("Stop", {"InstanceID": "A_ARG_TYPE_InstanceID"}, {})
    async def stop(self, InstanceID: int):
        instance(InstanceID)
        await self.backend.stop(owner="dlna")
        return {}

    @callable_action(
        "GetTransportInfo",
        {"InstanceID": "A_ARG_TYPE_InstanceID"},
        {
            "CurrentTransportState": "TransportState",
            "CurrentTransportStatus": "TransportStatus",
            "CurrentSpeed": "TransportPlaySpeed",
        },
    )
    async def transport_info(self, InstanceID: int):
        instance(InstanceID)
        return {
            "CurrentTransportState": self.state(),
            "CurrentTransportStatus": "OK",
            "CurrentSpeed": "1",
        }

    @callable_action(
        "GetMediaInfo",
        {"InstanceID": "A_ARG_TYPE_InstanceID"},
        {
            "NrTracks": "NumberOfTracks",
            "MediaDuration": "CurrentMediaDuration",
            "CurrentURI": "AVTransportURI",
            "CurrentURIMetaData": "AVTransportURIMetaData",
            "NextURI": "AVTransportURI",
            "NextURIMetaData": "AVTransportURIMetaData",
            "PlayMedium": "PlaybackStorageMedium",
            "RecordMedium": "RecordStorageMedium",
            "WriteStatus": "RecordMediumWriteStatus",
        },
    )
    async def media_info(self, InstanceID: int):
        instance(InstanceID)
        return {
            "NrTracks": int(self.loaded is not None),
            "MediaDuration": "00:00:00",
            "CurrentURI": self.loaded.source if self.loaded else "",
            "CurrentURIMetaData": self.metadata,
            "NextURI": "",
            "NextURIMetaData": "",
            "PlayMedium": "NETWORK",
            "RecordMedium": "NOT_IMPLEMENTED",
            "WriteStatus": "NOT_IMPLEMENTED",
        }

    @callable_action(
        "GetPositionInfo",
        {"InstanceID": "A_ARG_TYPE_InstanceID"},
        {
            "Track": "CurrentTrack",
            "TrackDuration": "CurrentTrackDuration",
            "TrackMetaData": "AVTransportURIMetaData",
            "TrackURI": "AVTransportURI",
            "RelTime": "RelativeTimePosition",
            "AbsTime": "AbsoluteTimePosition",
            "RelCount": "RelativeCounterPosition",
            "AbsCount": "AbsoluteCounterPosition",
        },
    )
    async def position_info(self, InstanceID: int):
        instance(InstanceID)
        return {
            "Track": int(self.loaded is not None),
            "TrackDuration": "00:00:00",
            "TrackMetaData": self.metadata,
            "TrackURI": self.loaded.source if self.loaded else "",
            "RelTime": "NOT_IMPLEMENTED",
            "AbsTime": "NOT_IMPLEMENTED",
            "RelCount": 2147483647,
            "AbsCount": 2147483647,
        }

    @callable_action(
        "GetCurrentTransportActions",
        {"InstanceID": "A_ARG_TYPE_InstanceID"},
        {"Actions": "CurrentTransportActions"},
    )
    async def transport_actions(self, InstanceID: int):
        instance(InstanceID)
        return {"Actions": self.actions_available()}

    @callable_action(
        "GetDeviceCapabilities",
        {"InstanceID": "A_ARG_TYPE_InstanceID"},
        {
            "PlayMedia": "PossiblePlaybackStorageMedia",
            "RecMedia": "PossibleRecordStorageMedia",
            "RecQualityModes": "PossibleRecordQualityModes",
        },
    )
    async def capabilities(self, InstanceID: int):
        instance(InstanceID)
        return {
            "PlayMedia": "NETWORK",
            "RecMedia": "NOT_IMPLEMENTED",
            "RecQualityModes": "NOT_IMPLEMENTED",
        }

    @callable_action(
        "GetTransportSettings",
        {"InstanceID": "A_ARG_TYPE_InstanceID"},
        {"PlayMode": "CurrentPlayMode", "RecQualityMode": "CurrentRecordQualityMode"},
    )
    async def settings(self, InstanceID: int):
        instance(InstanceID)
        return {"PlayMode": "NORMAL", "RecQualityMode": "NOT_IMPLEMENTED"}


class Rendering(AudioService):
    SERVICE_DEFINITION = definition("RenderingControl")
    STATE_VARIABLE_DEFINITIONS: ClassVar[dict] = {
        "A_ARG_TYPE_InstanceID": create_state_var("ui4"),
        "A_ARG_TYPE_Channel": create_state_var("string", allowed=["Master"]),
        "Volume": create_state_var(
            "ui2", allowed_range={"minimum": "0", "maximum": "100", "step": "1"}
        ),
        "Mute": create_state_var("boolean"),
        "PresetNameList": create_state_var("string", default="FactoryDefaults"),
        "A_ARG_TYPE_PresetName": create_state_var(
            "string", allowed=["FactoryDefaults"]
        ),
        "LastChange": create_event_var(
            "string",
            default='<Event xmlns="urn:schemas-upnp-org:metadata-1-0/RCS/"><InstanceID val="0" /></Event>',
        ),
    }

    async def volume(self, level=None, muted=None):
        backend = self.device.service(
            "urn:schemas-upnp-org:service:AVTransport:1"
        ).backend
        # The lock keeps a network volume command from racing with an alarm start.
        async with backend._lock:
            if (
                (level is not None or muted is not None)
                and backend.sound
                and backend.priority > Priority.LOW
            ):
                raise fault(701, "Higher priority audio is active")
            try:
                result = await asyncio.to_thread(output_volume, level, muted)
            except (pulsectl.PulseError, OSError) as err:
                raise fault(501, "Audio output unavailable") from err
        root = ET.Element("Event", xmlns="urn:schemas-upnp-org:metadata-1-0/RCS/")
        item = ET.SubElement(root, "InstanceID", val="0")
        ET.SubElement(
            item, "Volume", channel="Master", val=str(round(result.level * 100))
        )
        ET.SubElement(item, "Mute", channel="Master", val=str(int(result.muted)))
        self.state_variable("LastChange").value = ET.tostring(root, encoding="unicode")
        return result

    @callable_action(
        "GetVolume",
        {"InstanceID": "A_ARG_TYPE_InstanceID", "Channel": "A_ARG_TYPE_Channel"},
        {"CurrentVolume": "Volume"},
    )
    async def get_volume(self, InstanceID: int, Channel: str):
        instance(InstanceID)
        return {"CurrentVolume": round((await self.volume()).level * 100)}

    @callable_action(
        "SetVolume",
        {
            "InstanceID": "A_ARG_TYPE_InstanceID",
            "Channel": "A_ARG_TYPE_Channel",
            "DesiredVolume": "Volume",
        },
        {},
    )
    async def set_volume(self, InstanceID: int, Channel: str, DesiredVolume: int):
        instance(InstanceID)
        await self.volume(level=DesiredVolume / 100)
        return {}

    @callable_action(
        "GetMute",
        {"InstanceID": "A_ARG_TYPE_InstanceID", "Channel": "A_ARG_TYPE_Channel"},
        {"CurrentMute": "Mute"},
    )
    async def get_mute(self, InstanceID: int, Channel: str):
        instance(InstanceID)
        return {"CurrentMute": (await self.volume()).muted}

    @callable_action(
        "SetMute",
        {
            "InstanceID": "A_ARG_TYPE_InstanceID",
            "Channel": "A_ARG_TYPE_Channel",
            "DesiredMute": "Mute",
        },
        {},
    )
    async def set_mute(self, InstanceID: int, Channel: str, DesiredMute: bool):
        instance(InstanceID)
        await self.volume(muted=DesiredMute)
        return {}

    @callable_action(
        "ListPresets",
        {"InstanceID": "A_ARG_TYPE_InstanceID"},
        {"CurrentPresetNameList": "PresetNameList"},
    )
    async def list_presets(self, InstanceID: int):
        instance(InstanceID)
        return {"CurrentPresetNameList": "FactoryDefaults"}

    @callable_action(
        "SelectPreset",
        {"InstanceID": "A_ARG_TYPE_InstanceID", "PresetName": "A_ARG_TYPE_PresetName"},
        {},
    )
    async def select_preset(self, InstanceID: int, PresetName: str):
        instance(InstanceID)
        return {}


class Connection(AudioService):
    SERVICE_DEFINITION = definition("ConnectionManager")
    STATE_VARIABLE_DEFINITIONS: ClassVar[dict] = {
        "SourceProtocolInfo": create_event_var("string", default=""),
        "SinkProtocolInfo": create_event_var("string", default=PROTOCOLS),
        "CurrentConnectionIDs": create_event_var("string", default="0"),
        "A_ARG_TYPE_ConnectionID": create_state_var("i4"),
        "A_ARG_TYPE_RcsID": create_state_var("i4"),
        "A_ARG_TYPE_AVTransportID": create_state_var("i4"),
        "A_ARG_TYPE_ProtocolInfo": create_state_var("string"),
        "A_ARG_TYPE_ConnectionManager": create_state_var("string"),
        "A_ARG_TYPE_Direction": create_state_var("string", allowed=["Input"]),
        "A_ARG_TYPE_ConnectionStatus": create_state_var("string", allowed=["OK"]),
    }

    @callable_action(
        "GetProtocolInfo",
        {},
        {"Source": "SourceProtocolInfo", "Sink": "SinkProtocolInfo"},
    )
    async def protocol_info(self):
        return {"Source": "", "Sink": PROTOCOLS}

    @callable_action(
        "GetCurrentConnectionIDs", {}, {"ConnectionIDs": "CurrentConnectionIDs"}
    )
    async def connection_ids(self):
        return {"ConnectionIDs": "0"}

    @callable_action(
        "GetCurrentConnectionInfo",
        {"ConnectionID": "A_ARG_TYPE_ConnectionID"},
        {
            "RcsID": "A_ARG_TYPE_RcsID",
            "AVTransportID": "A_ARG_TYPE_AVTransportID",
            "ProtocolInfo": "A_ARG_TYPE_ProtocolInfo",
            "PeerConnectionManager": "A_ARG_TYPE_ConnectionManager",
            "PeerConnectionID": "A_ARG_TYPE_ConnectionID",
            "Direction": "A_ARG_TYPE_Direction",
            "Status": "A_ARG_TYPE_ConnectionStatus",
        },
    )
    async def connection_info(self, ConnectionID: int):
        if ConnectionID != 0:
            raise fault(706, "Invalid ConnectionID")
        return {
            "RcsID": 0,
            "AVTransportID": 0,
            "ProtocolInfo": "",
            "PeerConnectionManager": "",
            "PeerConnectionID": -1,
            "Direction": "Input",
            "Status": "OK",
        }
