"""Validate remote DLNA inputs as audio before handing them to playback."""

import asyncio
import json
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import ParseError

from async_upnp_client.exceptions import UpnpActionError
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from .playback import Sound


def fault(code: int, message: str) -> UpnpActionError:
    return UpnpActionError(error_code=code, error_desc=message)


async def audio_source(uri: str, metadata: str) -> Sound:
    """Require an HTTP audio resource, including when its suffix is misleading."""
    url = urlsplit(uri)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
    ):
        raise fault(716, "HTTP audio resource required")
    title = unquote(PurePosixPath(url.path).name) or url.hostname
    if metadata:
        try:
            root = fromstring(metadata)
        except (ParseError, DefusedXmlException) as err:
            raise fault(402, "Invalid metadata") from err
        media_class = root.findtext(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}class")
        if media_class and not media_class.startswith("object.item.audioItem"):
            raise fault(714, "Only audio is supported")
        title = root.findtext(".//{http://purl.org/dc/elements/1.1/}title") or title
    process = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-protocol_whitelist",
        "http,https,tcp,tls,crypto",
        "-rw_timeout",
        "5000000",
        "-analyzeduration",
        "2000000",
        "-probesize",
        "1000000",
        "-show_entries",
        "stream=codec_type:stream_disposition=attached_pic",
        "-of",
        "json",
        uri,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(10):
            output, _ = await process.communicate()
        streams = json.loads(output).get("streams", [])
        has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
        has_video = any(
            stream.get("codec_type") == "video"
            and not stream.get("disposition", {}).get("attached_pic")
            for stream in streams
        )
        if process.returncode or not has_audio or has_video:
            raise fault(714, "Only audio is supported")
    except (TimeoutError, ValueError) as err:
        raise fault(716, "Could not inspect audio resource") from err
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
    return Sound(uri, title, local=False)
