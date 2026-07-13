# Volvo Wallbox for Home Assistant

Custom integration for Volvo-branded wallboxes using the official
[Volvo Energy Device API](https://developer.volvocars.com/apis/energy-device-api/v1/overview/).

## Features

- Consumption sensors: current session, today, this month, last session
  (Energy-dashboard compatible)
- Charging state sensor
- Start / pause charging buttons
- Charging and discharging (V2G/V2H) amp limit controls
- Services: charging schedules, session queries, RFID ID token management

## Prerequisites

1. A [Volvo developers account](https://developer.volvocars.com/) with an API
   application (gives you the **VCC API key** and OAuth **client ID/secret**).
   The application must include the Energy Device API scopes.
2. **Before first use:** verify the scope list in
   `custom_components/volvo_wallbox/const.py` (`SCOPES`) matches the scopes
   shown on the Energy Device API overview page in the developer portal.
3. Your wallbox ID (try the serial number from the Volvo Cars app or the
   unit's label — the config flow validates it and lets you retry).

## Installation

Copy `custom_components/volvo_wallbox` into your Home Assistant `config/custom_components/`
directory (or add this repository to HACS as a custom repository) and restart
Home Assistant.

## Configuration

1. Settings → Devices & services → Add integration → **Volvo Wallbox**.
2. Enter your OAuth client ID/secret when asked for application credentials.
3. Log in with your Volvo ID.
4. Enter your VCC API key.
5. Enter your wallbox ID.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest tests -v
```
