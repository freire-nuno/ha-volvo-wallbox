# CLAUDE.md — Volvo Wallbox integration

Home Assistant custom integration (`volvo_wallbox`) for Volvo-branded
wallboxes, built on the official Volvo Energy Device API. Architecture
mirrors the HA core `volvo` integration (Platinum): `application_credentials`
OAuth2 (Volvo ID, PKCE), an inline aiohttp client, one `DataUpdateCoordinator`,
entity-description-based platforms.

## Environment

- The system Python is 3.9 — never use it. The venv at `.venv/` was built
  with uv-managed Python 3.13 (`~/.local/bin/uv`). Recreate with:
  `uv venv .venv --python 3.13 --seed && uv pip install -p .venv/bin/python -r requirements_test.txt`
- Run tests from the repo root: `.venv/bin/python -m pytest tests -v`
  (49 tests; all must stay green). `pytest.ini` sets `asyncio_mode = auto` —
  do not change it, and tests need no `@pytest.mark.asyncio` markers.
- No linter is configured yet (see roadmap). Match the existing style.
- Reference implementation: the HA core `volvo` integration (same
  architecture, Platinum quality). Local copies:
  `~/projects/ha-core/homeassistant/components/volvo/` (full dev checkout)
  and `.venv/lib/python3.13/site-packages/homeassistant/components/volvo/`
  (vendored). Mirror its patterns when in doubt.

## Key files

- `custom_components/volvo_wallbox/api.py` — Energy Device API client +
  auth bridges + `ChargingSession`/`IdToken` models + exception hierarchy
  (`EnergyDeviceApiError` > `EnergyDeviceAuthError`, `WallboxOperationError`
  with `.code`). The OpenAPI contract is checked in at
  `docs/energy-device-api-specification.json` — verify against it before
  changing any endpoint call.
- `coordinator.py` — `WallboxData` + pure derivation functions
  (`find_current_session`, `find_last_completed_session`, `energy_since`) +
  `WallboxCoordinator` (fetches state + sessions since Jan 1 local, derives
  today/month/year). `type VolvoWallboxConfigEntry = ConfigEntry[WallboxCoordinator]`;
  `entry.runtime_data` is the coordinator.
- `entity.py` — base entity: `unique_id = f"{wallbox_id}_{key}"`,
  `translation_key = key`, one device per wallbox.
- Platforms: `sensor.py` (8), `button.py` (2), `number.py` (2, optimistic +
  RestoreNumber; note the `available` property override — `CoordinatorEntity.available`
  ignores `_attr_available` by MRO). `services.py` (7 services, device-id
  resolution via device registry).
- `strings.json` and `translations/en.json` MUST stay byte-identical
  (custom components load `translations/en.json` at runtime; `strings.json`
  is kept for a future core migration).
- `brand/` — self-hosted brand images (HA 2026.3+ mechanism; the
  home-assistant/brands repo no longer accepts custom-integration icons).
- `scripts/smoke_test.py` — standalone live-API test (PKCE flow in browser);
  validated against the real API on 2026-07-13.

## Conventions (enforced in review)

- All user-facing errors are `HomeAssistantError` with translation keys:
  `operation_failed` (WallboxOperationError, keep first — it's a subclass),
  `api_error` (other EnergyDeviceApiError). Never let raw API/aiohttp
  exceptions escape buttons/numbers/services.
- Coordinator error mapping: `EnergyDeviceAuthError` → `ConfigEntryAuthFailed`
  (triggers reauth); `EnergyDeviceApiError` → `UpdateFailed`.
- Tests: typed parameters, no conditionals/branching, `pytest.param` with
  `id=`, `@pytest.mark.usefixtures` for unused fixtures. Time-dependent
  tests freeze at `2026-07-12 12:00:00+00:00` (conftest mock sessions are
  July 2026; test hass runs in US/Pacific — "today" boundaries are LOCAL).
- Platform test modules patch `custom_components.volvo_wallbox.PLATFORMS`
  down to their own platform (historical artifact of parallel development;
  harmless and kept). `tests/test_coordinator.py` locally overrides
  `setup_integration` to skip platform forwarding — also intentional.
- `from __future__ import annotations` in every module. Minimal try blocks.
  Comments only for non-obvious constraints.

## Release process

1. Bump `version` in `custom_components/volvo_wallbox/manifest.json`
2. Commit, push to `main` (via PR or directly — repo owner's call)
3. `gh release create vX.Y.Z --target main --title ... --notes ...`
   (HACS installs from GitHub releases)

## Volvo API facts (hard-won, don't rediscover)

- Scopes (already correct in `const.py`): `openid` +
  `energy_device:user_id_token:readwrite`, `energy_device:wallbox:read`,
  `energy_device:wallbox:write`, `energy_device:wallbox:control`.
- No list-wallboxes endpoint — the wallbox ID is user-supplied and validated
  via `GET /wallbox/{id}`. Format: `WBVA1ABCD-WB24.01.2500001234`-style.
- `GET /wallbox/{id}` returns the wallbox IDENTITY string, not a state
  (confirmed live 2026-07-18). It is only used for config-flow validation;
  the charging-state sensor is DERIVED (open session → `charging`, else
  `idle`) and the coordinator polls only the sessions endpoint.
- The wallbox ID is the config entry `unique_id`. A future reconfigure flow
  must NOT allow changing it (mirror core volvo's VIN lock — recreate the
  entry instead); only the API key should be reconfigurable.
- Transient Volvo API errors make entities unavailable for one poll cycle
  (~1 min) and recover on the next — expected coordinator behavior, not a bug.
- `chargedEnergy` is treated as kWh (confirmed plausible against live data).
- Amp limits are write-only (no read-back) → numbers are optimistic.
- Rate limits: 10,000 requests/day per application (60 s polling ≈ 2,900/day).
- The owner's Volvo application is PUBLISHED (client ID permanent; the
  portal's "30 days" only means an old secret survives 30 days after a
  manual rotation). Open question: OAuth refresh-token grant duration —
  if users report periodic re-login prompts, that's Volvo's grant cap for
  non-partner apps, not a bug.
- The developer portal (developer.volvocars.com) 403-blocks automated
  fetching — ask the repo owner to grab portal-only facts manually.

## Roadmap

See `docs/ROADMAP.md`. Design spec and implementation plan for v0.1 live in
`docs/superpowers/`.
