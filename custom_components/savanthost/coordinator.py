"""Data update coordinator for Savant Host."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.components.climate import HVACMode

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    EVENT_HOMEASSISTANT_STOP,
    UnitOfTemperature,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SavantApi, SavantConnectionError
from .const import (
    ARG_COOL_POINT,
    ARG_HEAT_POINT,
    CMD_SET_COOL_POINT,
    CMD_SET_HEAT_POINT,
    DEFAULT_AVC_PORT,
    DEFAULT_PORT,
    DOMAIN,
    HA_TO_SAVANT_FAN_MODE,
    HA_TO_SAVANT_HVAC_MODE,
    HVAC_SCAN_INTERVAL,
    LOGGER,
    SCAN_INTERVAL,
    WS_RECONNECT_INTERVAL,
)
from .models import (
    SavantHostData,
    SavantThermostat,
    SavantThermostatState,
    apply_state_updates,
    apply_thermostat_state_updates,
    build_hvac_service_command,
    match_hvac_services,
    parse_configuration,
    parse_hvac_components,
    parse_lighting_devices,
    parse_loads,
    parse_rooms,
)
from .websocket import SavantAvcWebSocket

_LOGGER = logging.getLogger(__name__)

type SavantConfigEntry = ConfigEntry[SavantCoordinator]


class SavantCoordinator(DataUpdateCoordinator[SavantHostData]):
    """Coordinator for Savant Host data."""

    config_entry: SavantConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SavantConfigEntry) -> None:
        """Initialize the coordinator."""
        session = async_get_clientsession(hass)
        self._api = SavantApi(
            entry.data[CONF_HOST],
            session,
            entry.data.get(CONF_PORT, DEFAULT_PORT),
        )
        self._websocket = SavantAvcWebSocket(
            entry.data[CONF_HOST],
            DEFAULT_AVC_PORT,
            session,
        )
        self._ws_task: asyncio.Task[None] | None = None
        self._hvac_task: asyncio.Task[None] | None = None
        self._stop_listeners: CALLBACK_TYPE | None = None
        self.temperature_unit: str = UnitOfTemperature.FAHRENHEIT
        self.min_temp: float | None = None
        self.max_temp: float | None = None
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def async_shutdown(self) -> None:
        """Disconnect resources."""
        if self._ws_task is not None:
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task
            self._ws_task = None
        if self._hvac_task is not None:
            self._hvac_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._hvac_task
            self._hvac_task = None
        await self._websocket.async_disconnect()
        if self._stop_listeners is not None:
            self._stop_listeners()
            self._stop_listeners = None

    async def _async_update_data(self) -> SavantHostData:
        """Fetch Savant host data."""
        try:
            configuration_data = await self._api.async_get_active_configuration()
            lighting_data = await self._api.async_get_lighting_config()
            loads_data = await self._api.async_get_loads()
            hvac_components_data = await self._api.async_get_hvac_components()
            hvac_settings_data = await self._api.async_get_hvac_settings()
            services_data = await self._api.async_get_services()
        except SavantConnectionError as err:
            msg = "Error communicating with Savant host"
            raise UpdateFailed(msg) from err

        configuration = parse_configuration(configuration_data)
        self._async_register_hub_device(
            configuration.configuration_id, configuration.name
        )
        rooms = parse_rooms(lighting_data)
        devices = parse_lighting_devices(lighting_data)
        loads = parse_loads(loads_data, devices)

        temp_unit_raw = hvac_settings_data.get("temperatureUnits", "Fahrenheit")
        self.temperature_unit = (
            UnitOfTemperature.CELSIUS
            if temp_unit_raw.lower() == "celsius"
            else UnitOfTemperature.FAHRENHEIT
        )
        self.min_temp = _parse_optional_float(
            hvac_settings_data.get("temperatureMin")
            or hvac_settings_data.get("minTemperature")
        )
        self.max_temp = _parse_optional_float(
            hvac_settings_data.get("temperatureMax")
            or hvac_settings_data.get("maxTemperature")
        )

        thermostats_without_services = parse_hvac_components(hvac_components_data)
        service_bindings = match_hvac_services(
            services_data, thermostats_without_services
        )
        for device_id, thermostat in thermostats_without_services.items():
            if device_id not in service_bindings:
                LOGGER.warning(
                    "No HVAC service found for thermostat %s (%s); control disabled",
                    thermostat.name,
                    device_id,
                )
                continue
        thermostats = parse_hvac_components(
            hvac_components_data,
            service_bindings,
        )

        previous_states = self.data.states if self.data is not None else {}
        previous_thermostat_states = (
            self.data.thermostat_states if self.data is not None else {}
        )
        data = SavantHostData(
            configuration=configuration,
            rooms=rooms,
            loads=loads,
            states=previous_states,
            thermostats=thermostats,
            thermostat_states=previous_thermostat_states,
        )

        if self._ws_task is None and loads:
            self._start_websocket(data)

        if self._hvac_task is None and thermostats:
            self._start_hvac_poll(data)

        return data

    @callback
    def _handle_state_update(self, updates: dict[str, int]) -> None:
        """Handle WebSocket state updates."""
        if self.data is None:
            return
        self.async_set_updated_data(apply_state_updates(self.data, updates))

    def _start_websocket(self, data: SavantHostData) -> None:
        """Start the AVC WebSocket listener."""
        loads = data.loads

        async def listen() -> None:
            """Listen for WebSocket updates."""
            try:
                self.update_interval = None
                await self._websocket.async_listen(
                    loads,
                    self._handle_state_update,
                    WS_RECONNECT_INTERVAL.total_seconds(),
                )
            finally:
                self.update_interval = SCAN_INTERVAL
                self.hass.async_create_task(self.async_request_refresh())

        @callback
        def stop_websocket(_: Event) -> None:
            """Stop WebSocket on shutdown."""
            if self._ws_task is not None:
                self._ws_task.cancel()

        if self._stop_listeners is not None:
            self._stop_listeners()
        self._stop_listeners = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, stop_websocket
        )
        self._ws_task = self.config_entry.async_create_background_task(
            self.hass, listen(), "savanthost-avc-ws"
        )

    def _start_hvac_poll(self, _data: SavantHostData) -> None:
        """Start the periodic thermostat state polling task."""
        LOGGER.debug("Starting HVAC poll")

        async def poll() -> None:
            """Poll all thermostat states on a fixed interval."""
            while True:
                if self.data is not None and self.data.thermostats:
                    await self._async_poll_all_thermostats()
                await asyncio.sleep(HVAC_SCAN_INTERVAL.total_seconds())

        self._hvac_task = self.config_entry.async_create_background_task(
            self.hass, poll(), "savanthost-hvac-poll"
        )

    async def _async_fetch_state_value(self, state_name: str | None) -> str | None:
        """Fetch a single named state value, returning None on any error."""
        if state_name is None:
            return None
        try:
            result = await self._api.async_get_location_state(state_name)
            return str(result["value"])
        except SavantConnectionError, ValueError, KeyError:
            return None

    async def _async_poll_thermostat_state(
        self, thermostat: SavantThermostat
    ) -> SavantThermostatState:
        """Poll all state values for a single thermostat."""
        (
            temp_raw,
            mode_raw,
            fan_raw,
            cool_raw,
            heat_raw,
            action_raw,
            humidity_raw,
        ) = await asyncio.gather(
            self._async_fetch_state_value(thermostat.current_temp_state_name),
            self._async_fetch_state_value(thermostat.hvac_mode_state_name),
            self._async_fetch_state_value(thermostat.fan_mode_state_name),
            self._async_fetch_state_value(thermostat.cool_point_state_name),
            self._async_fetch_state_value(thermostat.heat_point_state_name),
            self._async_fetch_state_value(thermostat.hvac_action_state_name),
            self._async_fetch_state_value(thermostat.humidity_mode_state_name),
        )
        return SavantThermostatState(
            current_temperature=float(temp_raw) if temp_raw is not None else None,
            hvac_mode_raw=mode_raw,
            fan_mode_raw=fan_raw,
            cool_point=float(cool_raw) if cool_raw is not None else None,
            heat_point=float(heat_raw) if heat_raw is not None else None,
            hvac_action_raw=action_raw,
            humidity_mode_raw=humidity_raw,
        )

    async def _async_poll_all_thermostats(self) -> None:
        """Poll all thermostats and update coordinator data."""
        if self.data is None or not self.data.thermostats:
            return
        updates: dict[str, SavantThermostatState] = {}
        for device_id, thermostat in self.data.thermostats.items():
            updates[device_id] = await self._async_poll_thermostat_state(thermostat)
        self.async_set_updated_data(apply_thermostat_state_updates(self.data, updates))

    async def _async_poll_thermostat(self, device_id: str) -> None:
        """Poll a single thermostat after a command and update coordinator data."""
        if self.data is None:
            return
        thermostat = self.data.thermostats.get(device_id)
        if thermostat is None:
            return
        state = await self._async_poll_thermostat_state(thermostat)
        self.async_set_updated_data(
            apply_thermostat_state_updates(self.data, {device_id: state})
        )

    def _get_thermostat(self, device_id: str) -> SavantThermostat:
        """Return a thermostat or raise if missing or not controllable."""
        if self.data is None:
            msg = "Coordinator data not available"
            raise SavantConnectionError(msg)
        thermostat = self.data.thermostats.get(device_id)
        if thermostat is None:
            msg = f"Thermostat {device_id} not found"
            raise SavantConnectionError(msg)
        if thermostat.service is None:
            msg = f"Thermostat {thermostat.name} has no service binding"
            raise SavantConnectionError(msg)
        return thermostat

    async def async_send_thermostat_command(
        self,
        device_id: str,
        command: str,
        extra_arguments: dict[str, str] | None = None,
    ) -> None:
        """Send a command to a thermostat via POST /config/v1/services."""
        thermostat = self._get_thermostat(device_id)
        body = build_hvac_service_command(
            thermostat.service,
            thermostat.thermostat_address,
            command,
            extra_arguments,
        )
        await self._api.async_execute_service(body)
        await self._async_poll_thermostat(device_id)

    async def async_set_thermostat_hvac_mode(
        self, device_id: str, hvac_mode: HVACMode
    ) -> None:
        """Set the HVAC mode for a thermostat."""
        command = HA_TO_SAVANT_HVAC_MODE.get(hvac_mode)
        if command is None:
            msg = f"Unsupported HVAC mode: {hvac_mode}"
            raise SavantConnectionError(msg)
        await self.async_send_thermostat_command(device_id, command)

    async def async_set_thermostat_temperature(
        self,
        device_id: str,
        *,
        heat: float | None = None,
        cool: float | None = None,
    ) -> None:
        """Set heat and/or cool setpoints for a thermostat."""
        if heat is not None:
            await self.async_send_thermostat_command(
                device_id,
                CMD_SET_HEAT_POINT,
                {ARG_HEAT_POINT: str(int(heat) if heat == int(heat) else heat)},
            )
        if cool is not None:
            await self.async_send_thermostat_command(
                device_id,
                CMD_SET_COOL_POINT,
                {ARG_COOL_POINT: str(int(cool) if cool == int(cool) else cool)},
            )

    async def async_set_thermostat_fan_mode(
        self, device_id: str, fan_mode: str
    ) -> None:
        """Set the fan mode for a thermostat."""
        command = HA_TO_SAVANT_FAN_MODE.get(fan_mode.lower())
        if command is None:
            msg = f"Unsupported fan mode: {fan_mode}"
            raise SavantConnectionError(msg)
        await self.async_send_thermostat_command(device_id, command)

    async def async_turn_on_load(self, load_id: str, brightness: int | None) -> None:
        """Turn on a load, optionally setting brightness."""
        if brightness is not None:
            load_level = round(brightness * 100 / 255)
            await self._api.async_set_load_level(load_id, load_level)
            return
        await self._api.async_turn_on_load(load_id)

    async def async_turn_off_load(self, load_id: str) -> None:
        """Turn off a load."""
        await self._api.async_turn_off_load(load_id)

    @callback
    def _async_register_hub_device(self, configuration_id: str, name: str) -> None:
        """Register the Savant host hub device."""
        device_registry = dr.async_get(self.hass)
        device_registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, configuration_id)},
            manufacturer="Savant",
            name=name,
            model="Host",
        )


def _parse_optional_float(value: Any) -> float | None:
    """Parse an optional float from HVAC settings."""
    if value is None:
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None
