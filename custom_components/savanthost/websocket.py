"""WebSocket client for Savant AVC lighting state updates."""

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import yarl
from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType

from .const import AVC_HANDSHAKE_TIMEOUT, AVC_WS_PROTOCOL
from .models import (
    WS_URI_DEVICE_RECOGNIZED,
    SavantLoad,
    parse_avc_state_update,
    parse_module_get_response,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

WS_URI_DEVICE_PRESENT = "session/devicePresent"
WS_URI_STATE_REGISTER = "state/register"

_LOGGER = logging.getLogger(__name__)

DEVICE_PRESENT_PAYLOAD = {
    "URI": WS_URI_DEVICE_PRESENT,
    "messages": [
        {
            "protocolVersion": "0.1",
            "device": {
                "name": "homeassistant",
                "version": "1.0",
                "app": "homeassistant",
                "ip": "127.0.0.1",
                "model": "server",
            },
        }
    ],
}


class SavantAvcWebSocket:
    """Savant AVC lighting WebSocket client."""

    def __init__(
        self,
        host: str,
        port: int,
        session: ClientSession,
    ) -> None:
        """Initialize the WebSocket client."""
        self._host = host
        self._port = port
        self._session = session
        self._ws_url = yarl.URL.build(scheme="ws", host=host, port=port)
        self._ws: ClientWebSocketResponse | None = None
        self._loads: dict[str, SavantLoad] = {}
        _LOGGER.debug(
            "Initialized SavantAvcWebSocket with host: %s, port: %s, ws_url: %s",
            host,
            port,
            self._ws_url,
        )

    async def async_validate_handshake(self) -> None:
        """Connect and complete the AVC session handshake."""
        async with asyncio.timeout(AVC_HANDSHAKE_TIMEOUT):
            async with self._session.ws_connect(
                self._ws_url,
                protocols=[AVC_WS_PROTOCOL],
                heartbeat=30,
            ) as ws:
                await ws.send_json(DEVICE_PRESENT_PAYLOAD)
                async for msg in ws:
                    if msg.type in (
                        WSMsgType.CLOSED,
                        WSMsgType.CLOSING,
                        WSMsgType.ERROR,
                    ):
                        error_msg = "AVC WebSocket closed during handshake"
                        raise ConnectionError(error_msg)
                    if msg.type != WSMsgType.TEXT:
                        continue
                    payload = json.loads(msg.data)
                    uri = payload.get("URI") or payload.get("uri")
                    if uri == WS_URI_DEVICE_RECOGNIZED:
                        return
        timeout_msg = "AVC WebSocket handshake timed out"
        raise TimeoutError(timeout_msg)

    async def async_listen(
        self,
        loads: dict[str, SavantLoad],
        on_update: Callable[[dict[str, int]], Awaitable[None] | None],
        reconnect_interval: float,
    ) -> None:
        """Connect, subscribe, and process updates until cancelled."""
        self._loads = loads
        _LOGGER.debug("Listening for AVC state updates for %d loads", len(loads))
        while True:
            try:
                await self._async_connect_and_listen(on_update)
            except asyncio.CancelledError:
                await self.async_disconnect()
                raise
            except Exception:
                _LOGGER.exception("Savant AVC WebSocket error")
            finally:
                await self.async_disconnect()

            _LOGGER.debug(
                "Savant AVC WebSocket reconnecting in %s seconds",
                reconnect_interval,
            )
            await asyncio.sleep(reconnect_interval)

    async def _async_connect_and_listen(
        self,
        on_update: Callable[[dict[str, int]], Awaitable[None] | None],
    ) -> None:
        """Connect and process messages until the connection closes."""
        _LOGGER.debug("Connecting to AVC WebSocket")
        async with self._session.ws_connect(
            self._ws_url,
            protocols=[AVC_WS_PROTOCOL],
            heartbeat=30,
        ) as ws:
            self._ws = ws
            await ws.send_json(DEVICE_PRESENT_PAYLOAD)
            recognized = False
            device_addresses = {load.device_address for load in self._loads.values()}

            async for msg in ws:
                if msg.type in (WSMsgType.CLOSED, WSMsgType.CLOSING):
                    break
                if msg.type == WSMsgType.ERROR:
                    _LOGGER.warning("Savant AVC WebSocket error: %s", ws.exception())
                    break
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    payload = json.loads(msg.data)
                    _LOGGER.debug("Received AVC message: %s", payload)
                except json.JSONDecodeError, TypeError:
                    _LOGGER.debug("Ignoring non-JSON WebSocket message")
                    continue

                uri = payload.get("URI") or payload.get("uri")
                if not recognized and uri == WS_URI_DEVICE_RECOGNIZED:
                    recognized = True
                    _LOGGER.debug("AVC session recognized")
                    await ws.send_json(
                        {
                            "URI": WS_URI_STATE_REGISTER,
                            "messages": [{"state": "module"}],
                        }
                    )
                    for device_address in sorted(device_addresses):
                        _LOGGER.debug("Getting module for device %s", device_address)
                        await ws.send_json(
                            {
                                "URI": f"state/module/{device_address}/get",
                                "messages": [{}],
                            }
                        )
                    continue

                updates = parse_avc_state_update(payload, self._loads)
                updates |= parse_module_get_response(payload, self._loads)
                if not updates:
                    continue
                _LOGGER.debug("AVC load updates: %s", updates)
                result = on_update(updates)
                if asyncio.iscoroutine(result):
                    await result

    async def async_disconnect(self) -> None:
        """Disconnect the WebSocket."""
        if self._ws is not None and not self._ws.closed:
            _LOGGER.debug("Disconnecting AVC WebSocket")
            await self._ws.close()
        self._ws = None
