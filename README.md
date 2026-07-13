# Volvo Wallbox for Home Assistant

Custom integration for Volvo-branded wallboxes using the official
[Volvo Energy Device API](https://developer.volvocars.com/apis/energy-device-api/v1/overview/).

## Features

- Consumption sensors: current session, today, this month, this year,
  last session (Energy-dashboard compatible)
- Charging state sensor
- Start / pause charging buttons
- Charging and discharging (V2G/V2H) amp limit controls
- Services: charging schedules, session queries, RFID ID token management

## What gets added to Home Assistant

One **device** per configured wallbox (named *Volvo Wallbox*, serial = wallbox
ID) with the following entities and services.

### Sensors

| Entity | Description |
|---|---|
| `sensor.volvo_wallbox_charging_state` | Wallbox state as reported by the API |
| `sensor.volvo_wallbox_current_session_energy` | Energy of the ongoing charging session (kWh); `0.0` when idle |
| `sensor.volvo_wallbox_energy_today` | Energy charged today (kWh, local-day boundary) — usable in the Energy dashboard |
| `sensor.volvo_wallbox_energy_this_month` | Energy charged this month (kWh) — usable in the Energy dashboard |
| `sensor.volvo_wallbox_energy_this_year` | Energy charged this year (kWh) — usable in the Energy dashboard |
| `sensor.volvo_wallbox_last_session_energy` | Energy of the last completed session (kWh) |
| `sensor.volvo_wallbox_last_session_start` | Start of the last completed session (timestamp, diagnostic) |
| `sensor.volvo_wallbox_last_session_end` | End of the last completed session (timestamp, diagnostic) |

### Buttons

| Entity | Description |
|---|---|
| `button.volvo_wallbox_start_charging` | Start charging |
| `button.volvo_wallbox_pause_charging` | Pause charging |

### Numbers

| Entity | Description |
|---|---|
| `number.volvo_wallbox_charging_amp_limit` | Charging current limit, 6–32 A (write-only on the API, so the value is optimistic and restored across restarts) |
| `number.volvo_wallbox_discharging_amp_limit` | Discharging (V2G/V2H) current limit, 0–32 A; becomes unavailable if the wallbox reports it unsupported |

### Services (actions)

| Service | Description |
|---|---|
| `volvo_wallbox.start_charging` | Start charging, optionally on behalf of an RFID ID token |
| `volvo_wallbox.apply_charging_schedule` | Apply a transactional charging schedule (watt- or ampere-based periods) |
| `volvo_wallbox.get_charging_sessions` | Return charging sessions in a time range as response data |
| `volvo_wallbox.read_id_token` | Put the wallbox in RFID-learn mode to read a new token |
| `volvo_wallbox.add_id_token` | Register a new RFID ID token on your account |
| `volvo_wallbox.update_id_token` | Rename an existing RFID ID token |
| `volvo_wallbox.delete_id_token` | Remove an RFID ID token from your account |

### Other capabilities

- **Config flow** with Volvo ID OAuth2 login (PKCE), live validation of the
  VCC API key and wallbox ID, and re-authentication when the token expires
- **Options flow**: polling interval (30–600 s, default 60)
- **Diagnostics** download with tokens, API key, and RFID tokens redacted

## Prerequisites

1. A [Volvo developers account](https://developer.volvocars.com/) with an API
   application (gives you the **VCC API key** and OAuth **client ID/secret**).
   The application must include the Energy Device API scopes.
2. **Before first use:** verify the scope list in
   `custom_components/volvo_wallbox/const.py` (`SCOPES`) matches the scopes
   shown on the Energy Device API overview page in the developer portal.
3. Your wallbox ID (try the serial number from the Volvo Cars app or the
   unit's label — the config flow validates it and lets you retry). It looks
   like `WBVA1ABCD-WB24.01.2500001234` (a product code, `-WB`, then a
   dot-separated serial).

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
