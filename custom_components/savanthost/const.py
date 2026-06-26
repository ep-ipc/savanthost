"""Constants for the Savant Host integration."""

import logging
from datetime import timedelta

from homeassistant.components.climate import HVACMode
from homeassistant.const import Platform

DOMAIN = "savanthost"

HVAC_SERVICE_TYPES = frozenset({"SVC_ENV_HVAC", "SVC_ENV_SINGLE_SETPOINT_HVAC"})

# Minimum zone match score before logging a weak HVAC service binding warning.
HVAC_SERVICE_MATCH_MIN_SCORE = 70

CMD_SET_HVAC_MODE_OFF = "SetHVACModeOff"
CMD_SET_HVAC_MODE_HEAT = "SetHVACModeHeat"
CMD_SET_HVAC_MODE_COOL = "SetHVACModeCool"
CMD_SET_HVAC_MODE_AUTO = "SetHVACModeAuto"
CMD_SET_HEAT_POINT = "SetHeatPointTemperature"
CMD_SET_COOL_POINT = "SetCoolPointTemperature"
CMD_SET_FAN_MODE_AUTO = "SetFanModeAuto"
CMD_SET_FAN_MODE_ON = "SetFanModeOn"

ARG_THERMOSTAT_ADDRESS = "ThermostatAddress"
ARG_HEAT_POINT = "HeatPointTemperature"
ARG_COOL_POINT = "CoolPointTemperature"

HA_TO_SAVANT_HVAC_MODE: dict[HVACMode, str] = {
    HVACMode.OFF: CMD_SET_HVAC_MODE_OFF,
    HVACMode.HEAT: CMD_SET_HVAC_MODE_HEAT,
    HVACMode.COOL: CMD_SET_HVAC_MODE_COOL,
    HVACMode.HEAT_COOL: CMD_SET_HVAC_MODE_AUTO,
}

HA_TO_SAVANT_FAN_MODE: dict[str, str] = {
    "auto": CMD_SET_FAN_MODE_AUTO,
    "on": CMD_SET_FAN_MODE_ON,
}

DEFAULT_PORT = 3060
DEFAULT_AVC_PORT = 8480
AVC_WS_PROTOCOL = "savant_protocol"

PLATFORMS = [Platform.CLIMATE, Platform.LIGHT]

SCAN_INTERVAL = timedelta(seconds=60)
WS_RECONNECT_INTERVAL = timedelta(minutes=5)
HVAC_SCAN_INTERVAL = timedelta(seconds=45)
AVC_HANDSHAKE_TIMEOUT = 10

LOGGER = logging.getLogger(__package__)
