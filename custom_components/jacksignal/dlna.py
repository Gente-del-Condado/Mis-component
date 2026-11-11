"""Optional LAN audio renderer with SSDP discovery and SOAP/GENA control."""

import asyncio
import json
import shutil
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from functools import partial
from ipaddress import IPv4Address, ip_address
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from aiohttp import web
from async_upnp_client.const import DeviceInfo
from async_upnp_client.server import (
    EventSubscriber,
    UpnpServer,
    UpnpServerDevice,
    action_handler,
    to_xml,
    unsubscribe_handler,
)

from .dlna_services import Connection, Rendering, Transport

DLNA = "dlna"
DEFAULT_NAME = "JackSignal Audio"


def receiver_name(value):
    """Allow readable Unicode names without XML-invalid control characters."""
    if not isinstance(value, str):
        raise ValueError("Invalid receiver name")
    name = value.strip()
    if not 1 <= len(name) <= 64 or any(not char.isprintable() for char in name):
        raise ValueError("Invalid receiver name")
    return name


def settings(value):
    """Use an explicitly selected local IPv4 address for discovery and HTTP."""
    name = receiver_name(value.get("name", DEFAULT_NAME))
    if not value.get("enabled", False):
        return None
    address = IPv4Address(value["address"])
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        raise ValueError("Choose the Raspberry's LAN IPv4 address")
    port = int(value.get("port", 49200))
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid HTTP port")
    return str(address), port, bool(value.get("discovery", True)), name


@web.middleware
async def local_callbacks(request, handler):
    """Event notifications can only call back to the subscribing controller."""
    if request.method == "SUBSCRIBE" and "CALLBACK" in request.headers:
        callback = request.headers["CALLBACK"]
        if not callback.startswith("<") or not callback.endswith(">"):
            raise web.HTTPPreconditionFailed()
        try:
            url = urlsplit(callback[1:-1])
            same_peer = ip_address(url.hostname) == ip_address(request.remote)
            if url.scheme != "http" or not same_peer or url.username or url.password:
                raise ValueError("Invalid callback")
        except (ValueError, TypeError):
            raise web.HTTPPreconditionFailed() from None
    return await handler(request)


class Subscriber(EventSubscriber):
    @property
    def uuid(self):
        return "uuid:" + super().uuid


async def subscribe(service, request):
    """Bound subscriptions and emit standard GENA SID/TIMEOUT headers."""
    sid = request.headers.get("SID")
    try:
        raw_timeout = request.headers.get("TIMEOUT", "Second-1800")
        timeout = (
            1800
            if raw_timeout.lower() == "second-infinite"
            else int(raw_timeout.removeprefix("Second-"))
        )
        timeout = max(30, min(timeout, 1800))
    except ValueError:
        raise web.HTTPBadRequest() from None
    service._subscribers[:] = [
        sub for sub in service._subscribers if sub.expiration > datetime.now()
    ]
    if sid:
        subscriber = service.get_subscriber(sid)
        if (
            subscriber is None
            or "CALLBACK" in request.headers
            or "NT" in request.headers
        ):
            raise web.HTTPPreconditionFailed()
        subscriber.timeout = timeout
    else:
        if (
            request.headers.get("NT") != "upnp:event"
            or "CALLBACK" not in request.headers
        ):
            raise web.HTTPPreconditionFailed()
        if len(service._subscribers) >= 32:
            raise web.HTTPServiceUnavailable()
        subscriber = Subscriber(request.headers["CALLBACK"][1:-1], timeout)
        service.add_subscriber(subscriber)
    response = web.Response(
        headers={"SID": subscriber.uuid, "TIMEOUT": f"Second-{timeout}"}
    )
    if sid is None:
        await response.prepare(request)
        await response.write_eof()
        await service.async_send_events(subscriber)
    return response


class AudioServer(UpnpServer):
    """Use the library's protocol handlers with bounded HTTP requests and cleanup."""

    discovery = True

    async def _async_start_ssdp(self):
        if self.discovery:
            await super()._async_start_ssdp()

    async def _async_start_http_server(self):
        @web.middleware
        async def diagnostics(request, handler):
            status = 500
            try:
                response = await handler(request)
                status = response.status
                return response
            except web.HTTPException as err:
                status = err.status
                raise
            finally:
                self.receiver.last_request = (
                    f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} · "
                    f"{request.remote} · {request.method} · HTTP {status}"
                )
                if status >= 400:
                    self.receiver.last_error = f"HTTP {status}"

        app = web.Application(client_max_size=65536, middlewares=[diagnostics, local_callbacks])
        app.router.add_get(self._device.device_url, partial(to_xml, self._device))
        for service in self._device.all_services:
            info = service.SERVICE_DEFINITION
            app.router.add_get(info.scpd_url, partial(to_xml, service))
            app.router.add_post(info.control_url, partial(action_handler, service))
            app.router.add_route(
                "SUBSCRIBE", info.event_sub_url, partial(subscribe, service)
            )
            app.router.add_route(
                "UNSUBSCRIBE", info.event_sub_url, partial(unsubscribe_handler, service)
            )
        self.runner = web.AppRunner(app, access_log=None, shutdown_timeout=5)
        await self.runner.setup()
        self._site = web.TCPSite(self.runner, self.source[0], self.http_port)
        await self._site.start()

    async def async_stop(self):
        try:
            await self._async_stop_ssdp()
        finally:
            await self._async_stop_http_server()

    async def _async_stop_ssdp(self):
        # The library's stop assumes startup completed and leaves its response socket open.
        if self._advertisement_announcer and self._advertisement_announcer._transport:
            await self._advertisement_announcer.async_stop()
        if self._search_responder:
            if self._search_responder._transport:
                await self._search_responder.async_stop()
            if self._search_responder._response_transport:
                self._search_responder._response_transport.close()

    async def _async_stop_http_server(self):
        if self._device:
            for service in self._device.all_services:
                service._subscribers.clear()
        if hasattr(self, "runner"):
            await self.runner.cleanup()


class DlnaReceiver:
    def __init__(self, playback, entry_id):
        self.playback = playback
        self.udn = f"uuid:{uuid5(NAMESPACE_URL, 'jacksignal:' + entry_id)}"
        self.server = None
        self.transport = None
        self._settings = None
        self._lock = asyncio.Lock()
        self.last_request = "—"
        self.last_error = "—"

    async def configure(self, options):
        desired = settings(options.get(DLNA, {}))
        async with self._lock:
            if desired == self._settings:
                return
            if desired and not await asyncio.to_thread(shutil.which, "ffprobe"):
                raise ValueError("FFprobe is required for audio validation")
            previous = self._settings
            await self._stop()
            try:
                if desired:
                    await self._start(desired)
            except Exception as err:
                self.last_error = type(err).__name__
                await self._stop()
                if previous:
                    await self._start(previous)
                raise

    async def _start(self, address):
        playback, udn = self.playback, self.udn
        host, port, discovery, name = address
        # Read packaged metadata off the event loop; never duplicate release numbers.
        manifest = json.loads(await asyncio.to_thread(
            Path(__file__).with_name("manifest.json").read_text, encoding="utf-8"
        ))

        class Renderer(UpnpServerDevice):
            DEVICE_DEFINITION = DeviceInfo(
                device_type="urn:schemas-upnp-org:device:MediaRenderer:1",
                friendly_name=name,
                manufacturer="JackSignal",
                manufacturer_url=None,
                model_description="Receptor exclusivo de audio con prioridades de Alarmo",
                model_name="JackSignal",
                model_number=manifest["version"],
                model_url=manifest["documentation"],
                serial_number=None,
                udn=udn,
                upc=None,
                presentation_url=None,
                url="/description.xml",
                icons=[],
                xml=ET.Element("device"),
            )
            EMBEDDED_DEVICES = ()
            SERVICES = (Transport, Rendering, Connection)

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                transport = self.service("urn:schemas-upnp-org:service:AVTransport:1")
                transport.backend = playback
                transport.publish()

        self.server = AudioServer(
            Renderer, (host, 0), http_port=port, boot_id=int(time.time())
        )
        self.server.discovery = discovery
        self.server.receiver = self
        await self.server.async_start()
        self.transport = self.server._device.service(
            "urn:schemas-upnp-org:service:AVTransport:1"
        )
        self.playback.listeners.add(self.transport.publish)
        self._settings = address

    def diagnostics(self):
        """Report runtime state, not merely saved options; omit media URLs/tokens."""
        active = self._settings
        return {
            "running": bool(active),
            "name": active[3] if active else "—",
            "discovery": bool(active and active[2]),
            "url": f"http://{active[0]}:{active[1]}/description.xml" if active else "—",
            "last_request": self.last_request,
            "last_error": self.last_error,
        }

    async def _stop(self):
        if self.transport:
            self.playback.listeners.discard(self.transport.publish)
            self.transport = None
        if self.server:
            try:
                await self.server.async_stop()
            finally:
                self.server = None
        self._settings = None
        await self.playback.stop(owner="dlna")

    async def close(self):
        async with self._lock:
            await self._stop()
