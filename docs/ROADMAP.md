# Roadmap

Open items carried over from the v0.1 development cycle (2026-07-12/14),
ordered roughly by value. Items marked *(review)* came out of the final
whole-branch code review; the full review history lived in the (git-ignored)
`.superpowers/` scratch dir, so this file is the durable record.

## Near-term

- **LICENSE file** — repo has none; blocks HACS default-store submission and
  any future library extraction. Owner to pick (MIT suggested).
- **CI workflows** — `.github/workflows/`: `hacs/action` validation
  (category: integration) + hassfest. Both required for HACS default store.
- **HACS default store submission** — after the two items above: PR adding
  the repo to the `integration` file at github.com/hacs/default (alphabetical
  order, submitted from the owner's account). Expect a months-long review
  queue; no effort while waiting.
- **Reconfigure flow** *(review)* — the design spec promised
  `async_step_reconfigure` (change API key / wallbox ID without re-adding);
  the plan dropped it silently. Mirror the core `volvo` implementation.
- **Ruff config** *(review)* — add ruff + run once; several multi-line
  ternary lambdas in `sensor.py` would be reformatted.

## When real-world data arrives

- **Charging-state enum** — `sensor.charging_state` passes the raw API
  string through because the state values are undocumented. Once observed
  values are known (from diagnostics of a live install), convert to
  `SensorDeviceClass.ENUM` with `options` + translations.
- **OAuth grant duration** — if periodic re-login prompts appear on a
  published app, document the observed cadence in the README.

## Hardening (deferred minors from review)

- Redact the wallbox ID/serial in diagnostics output.
- Include the wallbox ID in the device name (multi-wallbox households get
  identically-named devices today).
- Test coverage: number restore path (`async_get_last_number_data`),
  remaining `WallboxOperationErrorCodes` values.
- `services.yaml` `periods` uses a plain `object:` selector (no UI shape
  validation) — revisit if HA grows a structured list selector.

## Long-term: upstreaming to Home Assistant core

Prerequisites, in order:

1. Extract `api.py` into a published PyPI library (OSI license, tagged
   releases, public CI) — or contribute Energy Device API support to
   `volvocarsapi` (github.com/thomasddn/volvo-cars-api, same author as the
   core `volvo` integration).
2. Settle the domain question with @thomasddn / an architecture discussion:
   a new `volvo_wallbox` domain vs. extending core `volvo` (the wallbox
   shares the same Volvo ID cloud — precedent favors one domain per cloud,
   cf. `tesla_fleet`).
3. Bronze quality-scale audit; notably the `scan_interval` option must be
   removed (core forbids user-configurable polling) and `version` dropped
   from the manifest.
4. Port tests to core conventions; docs PR to home-assistant.io; PR to
   home-assistant/core following its PR template strictly.
