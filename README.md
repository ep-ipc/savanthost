# Savant Host — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

Home Assistant custom integration for lights and thermostats running on [Savant](https://www.savant.com/) hosts.

## Features

- Discovers Savant lighting and thermostat details from the host configuration
- Control light states and brightness
- Read and control thermostat states (HVAC mode, setpoints, fan mode)

## Prerequisites

- A Savant host with the Open API enabled and reachable on your network (this integration interacts with devices via the Savant host, and does not talk to the devices directly)
- Port 3060 (HTTP Open API) and port 8480 (AVC lighting WebSocket) accessible
- [HACS](https://hacs.xyz/) installed in Home Assistant

## Installation

### Via HACS (recommended)

1. Open **HACS** → **Integrations**.
2. Open the **⋮** menu → **Custom repositories**.
3. Add this repository URL and select category **Integration**:
   ```
   https://github.com/ep-ipc/savanthost
   ```
4. Search for **Savant Host** in HACS and click **Download**.
5. Restart Home Assistant.

### Manual

Copy the `custom_components/savanthost` folder into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings** → **Devices & Services**.
2. Click **Add Integration** and search for **Savant Host**.
3. Enter the host address and port (default `3060` for the HTTP Open API).

Setup validates both the HTTP Open API and the AVC WebSocket on port 8480.

## Development

For local development, a devcontainer configuration is present in this repository.  You can use VS Code (or VS Code derivatives like Cursor IDE) to build the dev container.

1. Clone this repository.
2. Open the cloned repository in VS Code.
3. When it prompts to re-open the repository with the dev container, accept it.
4. Once the container is built, open a terminal and run `scripts/develop` to start an instance of home assistant.

The savanthost custom component will be available in integrations immediately.

Note: Development scripts and devcontainer.json are based on [ludeeus/integration_blueprint](https://github.com/ludeeus/integration_blueprint).

### Lint checking

Linting uses `ruff`, configured in `.ruff.toml`.

- `scripts/lint` — format and auto-fix the entire repository (run manually).
- Pre-commit hook — check-only on staged Python files; blocks the commit on errors.

Git hooks are activated automatically when you run `scripts/setup` (including in the dev container). On a host system without running full setup:

```bash
git config --local core.hooksPath .githooks
python3 -m pip install ruff   # or: pip install -r requirements.txt
```

If the hook reports missing tooling, install `ruff` with one of the commands above.

## Savant Documentation

For background on how the Savant API and websocket works, check out [berfarah/savantserver](https://github.com/berfarah/savantserver) - they have done some excellent work in reverse engineering and documenting what they've learned to date.

