"""Constants for the Savant Host integration."""

import logging
from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "savanthost"

DEFAULT_PORT = 3060
DEFAULT_AVC_PORT = 8480
AVC_WS_PROTOCOL = "savant_protocol"

PLATFORMS = [Platform.CLIMATE, Platform.LIGHT]

SCAN_INTERVAL = timedelta(seconds=60)
WS_RECONNECT_INTERVAL = timedelta(minutes=5)
HVAC_SCAN_INTERVAL = timedelta(seconds=45)
AVC_HANDSHAKE_TIMEOUT = 10

LOGGER = logging.getLogger(__package__)
