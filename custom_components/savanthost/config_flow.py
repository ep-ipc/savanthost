"""Config flow for Savant Host."""

from typing import TYPE_CHECKING, Any

import voluptuous as vol
import yarl
from aiohttp import ClientError
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SavantApi, SavantConnectionError
from .const import DEFAULT_AVC_PORT, DEFAULT_PORT, DOMAIN
from .models import parse_configuration
from .websocket import SavantAvcWebSocket

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _normalize_host(host: str) -> str:
    """Normalize host by extracting hostname if a URL is provided."""
    try:
        return yarl.URL(host).host or host
    except ValueError:
        return host


async def _async_validate_host(
    hass: HomeAssistant, host: str, port: int
) -> dict[str, str]:
    """Validate host connectivity and return config entry data."""
    session = async_get_clientsession(hass)
    api = SavantApi(host, session, port)
    try:
        configuration = parse_configuration(await api.async_get_active_configuration())
        await api.async_get_lighting_config()
    except SavantConnectionError as err:
        raise CannotConnectError from err

    avc_ws = SavantAvcWebSocket(host, DEFAULT_AVC_PORT, session)
    try:
        await avc_ws.async_validate_handshake()
    except (ClientError, ConnectionError, OSError, TimeoutError) as err:
        raise CannotConnectAvcError from err

    return {
        "configuration_id": configuration.configuration_id,
        "name": configuration.name,
    }


class SavantHostConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Savant Host config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            port = user_input[CONF_PORT]
            try:
                result = await _async_validate_host(self.hass, host, port)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except CannotConnectAvcError:
                errors["base"] = "avc_cannot_connect"
            except HomeAssistantError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    result["configuration_id"], raise_on_progress=False
                )
                if self.source == SOURCE_RECONFIGURE:
                    entry = self._get_reconfigure_entry()
                    self._abort_if_unique_id_mismatch(
                        reason="unique_id_mismatch",
                        description_placeholders={
                            "configuration_id": entry.unique_id or "",
                        },
                    )
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={CONF_HOST: host, CONF_PORT: port},
                    )
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: host, CONF_PORT: port}
                )
                return self.async_create_entry(
                    title=result["name"],
                    data={CONF_HOST: host, CONF_PORT: port},
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
            }
        )
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            data_schema = self.add_suggested_values_to_schema(data_schema, entry.data)

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration."""
        return await self.async_step_user(user_input)


class CannotConnectError(HomeAssistantError):
    """Error to indicate we cannot connect to the Open API."""


class CannotConnectAvcError(HomeAssistantError):
    """Error to indicate we cannot connect to the AVC WebSocket."""
