# Volvo Wallbox — Home Assistant Custom Integration Design

**Date:** 2026-07-12
**Status:** Approved design, pending implementation plan

## Purpose

A Home Assistant custom integration (`volvo_wallbox`) for Volvo-branded wallboxes,
built on the official **Volvo Energy Device API**
(`https://api.volvocars.com/energy-device/v1`). Primary goal: consumption data
(charging session energy) in Home Assistant, including the Energy dashboard.
Secondary goals: charging controls, amp limits, schedules, and RFID token
management.

The integration mirrors the architecture of the Home Assistant core `volvo`
integration (Platinum quality), which uses the same Volvo ID OAuth2 stack, so it
can later be upstreamed (client extracted into the `volvocarsapi` PyPI library,
integration contributed to core).

A copy of the API's OpenAPI specification is checked in at
`docs/energy-device-api-specification.json`.

## Decisions made

- **Custom component first**, core contribution possibly later.
- **Self-contained**: the API client lives inline in the integration (allowed for
  custom components); no new PyPI dependency.
- **New standalone repo** (`ha-volvo-wallbox`), HACS-standard layout.
- **All four feature groups** in v1: consumption sensors, state + start/pause
  controls, amp limit numbers, schedule/RFID services.
- Wallbox ID is **entered by the user** in the config flow and validated live
  (the API has no list-wallboxes endpoint); the user does not know the ID yet, so
  validation must fail fast with a clear message to support trying candidates
  (serial number, PNC, ...).

## Repo layout

```
ha-volvo-wallbox/
├── custom_components/volvo_wallbox/
│   ├── __init__.py                  # entry setup, platform forwarding
│   ├── api.py                       # EnergyDeviceApi client + auth wrapper (aiohttp)
│   ├── application_credentials.py   # Volvo ID OAuth2 (PKCE)
│   ├── config_flow.py               # OAuth → API key → wallbox ID (validated)
│   ├── const.py
│   ├── coordinator.py               # DataUpdateCoordinator
│   ├── entity.py                    # base entity, shared device info
│   ├── sensor.py
│   ├── button.py
│   ├── number.py
│   ├── services.py + services.yaml
│   ├── diagnostics.py
│   ├── strings.json + translations/en.json
│   └── manifest.json
├── hacs.json
├── docs/energy-device-api-specification.json
└── README.md
```

## Authentication

Identical stack to the core `volvo` integration:

- `application_credentials` platform with `LocalOAuth2ImplementationWithPkce`
  against Volvo ID (same `AUTHORIZE_URL`/`TOKEN_URL` as `volvocarsapi.auth`:
  `https://volvoid.eu.volvocars.com/as/authorization.oauth2` and
  `.../as/token.oauth2`).
- `vcc-api-key` header on every request (the user's Volvo developer application
  key), plus OAuth2 Bearer token.
- Token refresh/reauth via HA's `OAuth2Session`; a small auth wrapper class in
  `api.py` bridges the session to the client (same pattern as
  `homeassistant/components/volvo/api.py`).

**Open item:** the OAuth scope list for the Energy Device API is not in the
OpenAPI spec. The user copies the scopes from the API's overview page on
developer.volvocars.com during implementation; scopes are a constant in
`const.py`.

## Config flow

1. **OAuth2 login** with Volvo ID (application credentials entered once).
2. **API key step**: enter VCC API key.
3. **Wallbox ID step**: enter the wallbox ID; validated live via
   `GET /wallbox/{id}`. On 404/403 show a clear error so the user can try
   candidate values. The wallbox ID is the config entry `unique_id`.
4. **Reauth** and **reconfigure** flows supported (mirroring `volvo`).
5. **Options flow**: polling interval (default 60 s).

## Data flow

One `DataUpdateCoordinator`, polling every 60 seconds (configurable):

1. `GET /wallbox/{id}` → wallbox/charging state.
2. `GET /wallbox/{id}/chargingsessions?start=<first-of-month>&end=<now>` →
   session list for the current month.

Derived in the coordinator from the sessions list: current (open) session,
last completed session, energy today, energy this month. 2 requests/minute is
well within Volvo API rate limits.

## Entities

All entities belong to one device (the wallbox; wallbox ID as serial).

| Platform | Entity | Source / behavior |
|---|---|---|
| sensor | Charging state | wallbox info value |
| sensor | Current session energy | open session's `chargedEnergy` (kWh); `0` when idle |
| sensor | Energy today | sum of sessions starting today; `total_increasing`, Energy-dashboard compatible |
| sensor | Energy this month | sum of month's sessions; `total_increasing` |
| sensor | Last session energy | most recent completed session (kWh) |
| sensor | Last session start / end | timestamps, diagnostic category |
| button | Start charging | `POST /wallbox/{id}/start` (no token) |
| button | Pause charging | `POST /wallbox/{id}/pause` |
| number | Charging amp limit | `POST /setChargingAmpLimit`; no read-back → optimistic/`assumed_state`, value restored across restarts |
| number | Discharging amp limit | `POST /setDischargingAmpLimit`; same pattern; marks itself unavailable on `NOT_SUPPORTED_BY_WALLBOX` |

## Services (actions)

- `volvo_wallbox.start_charging` — optional `id_token` (RFID) parameter.
- `volvo_wallbox.apply_charging_schedule` — start time + list of watt- or
  ampere-periods with durations (maps to `ApplyChargingScheduleRequest`).
- `volvo_wallbox.get_charging_sessions` — start/end range, optional `id_token`;
  returns sessions as response data (`SupportsResponse.ONLY`).
- `volvo_wallbox.read_id_token` — RFID-learn mode (`POST /readIdToken`).
- `volvo_wallbox.add_id_token` / `update_id_token` / `delete_id_token` — manage
  RFID tokens (`/user/idTokens`).

## Error handling

- **401** → trigger HA reauth flow (`ConfigEntryAuthFailed`).
- **429** → coordinator `UpdateFailed`, natural backoff via next poll.
- Command errors (409/422 `WallboxOperationError`) → raise `HomeAssistantError`
  with translated messages per code: `UNKNOWN_ERROR`, `WALLBOX_OFFLINE`,
  `WALLBOX_INCORRECT_STATUS`, `WALLBOX_IN_COOLDOWN`, `NOT_SUPPORTED_BY_WALLBOX`.
- Coordinator failures mark entities unavailable; recovery is automatic on next
  successful poll.

## Testing

- `pytest` with `pytest-homeassistant-custom-component`; aiohttp responses
  mocked.
- Config flow: happy path, invalid API key, invalid wallbox ID, reauth,
  reconfigure, options.
- Coordinator: session-derivation math (today/month sums, open session,
  midnight/month boundaries).
- Command error mapping (each `WallboxOperationErrorCodes` value).
- Entity behavior: numbers' optimistic state + restore; buttons calling the
  right endpoints.

## Out of scope (v1)

- Publishing the client to PyPI / upstreaming to `volvocarsapi`.
- Core contribution (quality-scale, brands imagery, etc.).
- HACS default-repository submission (repo will be HACS-compatible; submission
  is a later step).
- Long-term statistics backfill from historical sessions.
