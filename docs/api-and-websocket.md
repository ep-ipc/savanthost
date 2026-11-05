# Savant API, Websocket and Tools

These are the combined learnings of our own experience with reverse-engineering Savant's available APIs and websocket servers with significant input from the learnings found in [berfarah/savantserver](https://github.com/berfarah/savantserver) in the docs directory, which I highly recommend reviewing.

Since Savant is a closed ecosystem, official documentation is only available (as far as we know) to authorized Savant dealers.  We do our best to cover what's been found and how it works, but be aware that this could change at anytime.

## Overview

There are several interaction points with the Savant system.  The ones of interest to this Home Assistant integration are:

* Rest API on port 3060 - Provides configuration information about all devices, and SOME interaction with devices
* Feedback websocket at /feedback/v1/register port 3060 - read-only realtime feedback of device statuses on a ROOM level
* AVC Websocket server on port 8480 - provides read/write interaction at a device level

### Rest API

A swagger/OpenAPI page is available on the savant host at `http://yoursavanthost:3060/` and documents everything available from the REST API.

In this integration, the REST API is used for:

* Discovering devices and configurations
* Setting new states for lighting devices (turn on/off, set brightness level)
* Getting current state of thermostats (polling)
* Setting new states for thermostats

Here's a snippet of the endpoints relevant to this integration:

| Method | Endpoint | Returns |
|--------|----------|---------|
| GET | `/config/v1/rooms` | All rooms with UUIDs |
| GET | `/config/v1/rooms/{RoomID}` | Single room |
| GET | `/config/v1/room/{RoomID}/loads` | Loads for a specific room |
| GET | `/config/v1/lighting/devices` | All lighting devices |
| GET | `/config/v1/lighting/devices/{id}` | Device with loads and buttons |
| GET | `/config/v1/lighting/loads` | All lighting loads |
| GET | `/config/v1/lighting/loads/{id}` | Single load |
| GET | `/config/v1/lighting/scenes` | All lighting scenes |
| GET | `/config/v1/lighting/scenes/{id}` | Single scene with members |
| POST | `/control/v1/lighting/scenes/{id}/apply` | Apply a lighting scene |
| GET | `/config/v1/lighting/groups` | Lighting groups |
| GET | `/config/v1/lighting/buttons/{id}` | Button config |
| GET | `/config/v1/configuration/active` | Active config info |
| GET | `/config/v1/location/active` | Location with lat/lon, timezone |
| GET | `/config/v1/services` | All services (39) |
| GET | `/config/v1/services/{id}/commands` | Commands for a service |
| GET | `/config/v1/services/{id}/commands/{cmd}/arguments` | Arguments for a command |
| POST | `/config/v1/services` | Execute a command |
| GET | `/config/v2/services/events` | All service commands by room |
| GET | `/config/v1/shades/groups` | Shade groups |
| GET | `/config/v1/hvac/components` | HVAC components |
| GET | `/config/v1/hvac/components` | HVAC thermostat components (deviceID, roomID, capabilities) |
| GET | `/config/v1/hvac/components?RoomID={id}` | Components filtered by room |
| GET | `/feedback/v1/states/hvac` | Per-thermostat state name index (`Thermostats` map keyed by component name) |

### Read states

| Method | Endpoint | Returns |
|--------|----------|---------|
| GET | `/config/v1/location/state?state={name}` | `{"state":"<name>","value":"<value>"}` from StateCenter |

State names can contain spaces — pass them as the `state` query parameter (URL-encoded). The `value` field may be a string or number.

Examples:
```
GET /config/v1/location/state?state=Den.BrightnessLevel
  → {"state":"Den.BrightnessLevel","value":"95"}

GET /config/v1/location/state?state=1st%20Floor%20Guest%20Thermostat.HVAC_controller.ThermostatCurrentHeatPoint
  → {"state":"1st Floor Guest Thermostat.HVAC_controller.ThermostatCurrentHeatPoint","value":"72"}
```

If a state has no current value, the API returns HTTP 500 with `{"error":"state requested had no value"}`. This integration treats that as an empty value.

### Service command execution endpoint

The endpoint `POST /config/v1/services` executes commands on devices.

Body:

```json
{
  "command": "string",
  "component": "string",
  "logicalComponent": "string",
  "serviceVariantID": "string",
  "type": "string",
  "zone": "string"
}
```

Example:

```json
{
  "command": "SetFanModeAuto",
  "component": "1st Floor Guest Thermostat",
  "logicalComponent": "HVAC_controller",
  "serviceVariantID": "1",
  "type": "SVC_ENV_HVAC",
  "zone": "2nd Floor Master Bath",
  "arguments": {
    "ThermostatAddress": "1"
  }
}
```

To get all those bits, you take apart the service name retrieved from `/config/v1/services`.  For example, a response from `/config/v1/services`:

```
{
    "serviceID": "F24EAD1A-DB9F-47EC-8A7C-EAFCEC52CA75",
    "roomID": "7C23034C-A600-4B19-AAC5-281325454B05",
    "name": "SVC_ENV_HVAC",
    "serviceRequest": "Library-1st Floor Guest Thermostat-HVAC_controller-1-SVC_ENV_HVAC",
    "alias": "1st Floor Guest Thermostat",
    "brand": "",
    "displayName": "Climate",
    "commands": null
  }
```

Use the value of `serviceRequest`, which in the above example is:

```
Library-1st Floor Guest Thermostat-HVAC_controller-1-SVC_ENV_HVAC
```

The serviceRequest is dash-separated components.  The format:

```
(zone)-(source component)-(source logical component)-(service variant)-(service type)-(request)
```

The mapping:

| component from service request | POST body property | Example |
|--|--|--|
| zone | zone | Library |
| source component | alias | 1st Floor Guest Thermostat |
| source logical component | logicalComponent | HVAC_controller |
| service variant | serviceVariantID | 1 |
| service type | type | SVC_ENV_HVAC
| request | (no mapping) | |

Which would resolve to:

```json
{
  "command": "SetFanModeAuto",
  "component": "1st Floor Guest Thermostat",
  "logicalComponent": "HVAC_controller",
  "serviceVariantID": "1",
  "type": "SVC_ENV_HVAC",
  "zone": "2nd Floor Master Bath",
  "arguments": {
    "ThermostatAddress": "1"
  }
}
```

from sclibridge help:

```
 servicerequestcommand
      <dash separated service request: (zone)-(source component)-(source logical component)-(service variant)-(service type)-(request)> <first argument name> <first argument value> ...
```

Available thermostat commands that have been discovered:

SetCoolPointTemperature
SetEcoCoolPointTemperature
SetEcoHeatPointTemperature
SetFanModeAuto
SetFanModeOn
SetHeatPointTemperature
SetHumidityModeOff
SetHumidityModeOn
SetHumiditySetPoint
SetHVACModeAuto
SetHVACModeCool
SetHVACModeEco
SetHVACModeHeat
SetHVACModeOff

This integration uses `POST /config/v1/services` for thermostat control. Service routing fields are parsed from each thermostat's `serviceRequest` (matched by service `alias` == HVAC component `name`). The Home Assistant climate entity maps to these commands:

| HA action | Savant command |
|-----------|----------------|
| HVAC mode Off | `SetHVACModeOff` |
| HVAC mode Heat | `SetHVACModeHeat` |
| HVAC mode Cool | `SetHVACModeCool` |
| HVAC mode Heat/Cool (auto) | `SetHVACModeAuto` |
| Heat setpoint | `SetHeatPointTemperature` |
| Cool setpoint | `SetCoolPointTemperature` |
| Fan auto / on | `SetFanModeAuto` / `SetFanModeOn` |

Not yet exposed in Home Assistant: eco mode (`SetHVACModeEco`, eco setpoints) and humidity control (`SetHumidityMode*`, `SetHumiditySetPoint`). Humidity mode is readable as a state attribute.

### AVC Websocket

The AVC Websocket is used for:

* Getting current state of lighting devices (or "loads" as they're called in the Savant system) - arrives in realtime when changes occur

Why not use the API to get state?

* There doesn't appear to be anywhere in the API that exposes state information at a device level.  Only room level states could be found which isn't granular enough to work with individual devices.  (ex: it will say if any light is on in the kitchen, but not which light in the kitchen is on)
* The feedback websocket (served by the openapi-go service) also only returns state information at a room level.

Why not use the AVC Websocket to set state?

* You can set state for lighting via the websocket, however for other devices there's no documentation out there on how this works.  Since it was available in the API along with controlling thermostats (HVAC devices), it made sense to consolidate everyhting in one place.

