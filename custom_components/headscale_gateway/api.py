"""Cliente de solo lectura. Nunca sigue redirecciones con una credencial Bearer."""
import asyncio
import ipaddress
import json

import aiohttp
from yarl import URL


class GatewayError(Exception):
    """No se puede consultar el Gateway."""


class GatewayAuthError(GatewayError):
    """La credencial es inválida, ha caducado o carece de permiso de lectura."""


def normalize_url(value):
    """Admite montajes HTTPS; HTTP solo con una dirección loopback explícita."""
    try:
        url = URL(value)
        if not url.is_absolute() or url.user is not None or url.query_string or url.fragment:
            raise ValueError
        if url.scheme != 'https':
            if url.scheme != 'http' or not ipaddress.ip_address(url.host).is_loopback:
                raise ValueError
        if any(part == '..' for part in url.raw_path.split('/')):
            raise ValueError
        return str(url).rstrip('/')
    except (ValueError, TypeError):
        raise GatewayError('Use an HTTPS Gateway base URL without credentials or query') from None


class GatewayClient:
    def __init__(self, session, base_url, token, verify_ssl=True):
        self.session = session
        self.base_url = normalize_url(base_url)
        self.token = token
        self.verify_ssl = verify_ssl

    async def status(self):
        try:
            async with self.session.get(
                self.base_url + '/api/v1/status',
                headers={'Authorization': 'Bearer ' + self.token},
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=False,
                ssl=self.verify_ssl,
            ) as response:
                if response.status in (401, 403):
                    raise GatewayAuthError('Gateway rejected the read credential')
                if response.status != 200:
                    raise GatewayError('Gateway status request failed')
                raw = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        raise GatewayError('Gateway response exceeds 64 KiB')
                value = json.loads(raw)
                if not isinstance(value, dict) or not isinstance(value.get('vpn_connected'), bool):
                    raise GatewayError('Invalid Gateway status response')
                # No incorpora rutas completas, URL, licencias ni futuros campos arbitrarios
                # del estado del Gateway al estado o diagnóstico de Home Assistant.
                allowed = ('vpn_connected', 'vpn_identity_confirmed', 'lan_https_active',
                           'setup_required', 'services_active', 'uptime_seconds',
                           'certificate_source', 'domain', 'node', 'version')
                return {key: value[key] for key in allowed if key in value}
        except GatewayError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, UnicodeError):
            raise GatewayError('Unable to read Gateway status') from None
