"""Standalone smoke test for the Volvo Energy Device API — no Home Assistant needed.

Performs the Volvo ID OAuth2 authorization-code flow with PKCE in your browser,
then exercises the same API client the integration uses.

Prerequisites:
  1. An API application on https://developer.volvocars.com/ with the Energy
     Device API scopes and a redirect URI matching --redirect-uri below
     (add e.g. http://localhost:8123/auth/external/callback to the app).
  2. Update SCOPES in custom_components/volvo_wallbox/const.py with the scope
     list shown on the API's portal page.

Usage (from the repo root):
  .venv/bin/python scripts/smoke_test.py \
      --client-id YOUR_CLIENT_ID \
      --client-secret YOUR_CLIENT_SECRET \
      --vcc-api-key YOUR_VCC_API_KEY \
      [--wallbox-id CANDIDATE_ID] \
      [--redirect-uri http://localhost:8123/auth/external/callback]

Without --wallbox-id it validates auth + API key (lists your RFID ID tokens).
With --wallbox-id it also fetches wallbox state and the last 30 days of
charging sessions — the quickest way to discover which candidate ID is right.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp
from aiohttp import web

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.volvo_wallbox.api import (  # noqa: E402
    ConfigFlowAuth,
    EnergyDeviceApi,
    EnergyDeviceApiError,
)
from custom_components.volvo_wallbox.const import (  # noqa: E402
    AUTHORIZE_URL,
    SCOPES,
    TOKEN_URL,
)


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


async def _wait_for_code(redirect_uri: str) -> str:
    """Run a tiny local server and capture the ?code= from the OAuth redirect."""
    parsed = urlparse(redirect_uri)
    future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

    async def handler(request: web.Request) -> web.Response:
        code = request.query.get("code")
        if code and not future.done():
            future.set_result(code)
            return web.Response(text="Authorization received — you can close this tab.")
        return web.Response(
            status=400, text=f"No code in callback: {request.query_string}"
        )

    app = web.Application()
    app.router.add_get(parsed.path, handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", parsed.port or 80)
    await site.start()
    try:
        return await asyncio.wait_for(future, timeout=300)
    finally:
        await runner.cleanup()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    parser.add_argument("--vcc-api-key", required=True)
    parser.add_argument("--wallbox-id")
    parser.add_argument(
        "--redirect-uri", default="http://localhost:8123/auth/external/callback"
    )
    args = parser.parse_args()

    verifier, challenge = _pkce_pair()
    authorize = f"{AUTHORIZE_URL}?" + urlencode(
        {
            "response_type": "code",
            "client_id": args.client_id,
            "redirect_uri": args.redirect_uri,
            "scope": " ".join(SCOPES),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    print(f"Scopes requested: {' '.join(SCOPES)}")
    print("\nOpen this URL in your browser and log in with your Volvo ID:\n")
    print(f"  {authorize}\n")
    print(f"Waiting for the redirect on {args.redirect_uri} ...")

    code = await _wait_for_code(args.redirect_uri)
    print("Authorization code received; exchanging for a token...")

    async with aiohttp.ClientSession() as session:
        token_response = await session.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": args.redirect_uri,
                "client_id": args.client_id,
                "client_secret": args.client_secret,
                "code_verifier": verifier,
            },
        )
        token_body = await token_response.json()
        if token_response.status != 200 or "access_token" not in token_body:
            print(f"TOKEN EXCHANGE FAILED ({token_response.status}): {token_body}")
            print("Hint: check SCOPES in const.py and the app's redirect URI.")
            return 1
        print("Token obtained.\n")

        api = EnergyDeviceApi(
            session, ConfigFlowAuth(token_body["access_token"]), args.vcc_api_key
        )

        try:
            tokens = await api.async_get_id_tokens()
        except EnergyDeviceApiError as err:
            print(f"GET /user/idTokens FAILED: {err}")
            print("Hint: 403 here usually means wrong SCOPES or VCC API key.")
            return 1
        print(f"GET /user/idTokens OK — {len(tokens)} RFID token(s):")
        for token in tokens:
            print(f"  - {token.name}: {token.token}")

        if not args.wallbox_id:
            print("\nAuth + API key work. Re-run with --wallbox-id <candidate>")
            print("(serial number / PNC from the Volvo Cars app or unit label).")
            return 0

        try:
            state = await api.async_get_wallbox_state(args.wallbox_id)
        except EnergyDeviceApiError as err:
            print(f"\nGET /wallbox/{args.wallbox_id} FAILED: {err}")
            print("Hint: wrong wallbox ID — try another candidate.")
            return 1
        print(f"\nGET /wallbox/{args.wallbox_id} OK — state: {state}")

        now = datetime.now(UTC)
        sessions = await api.async_get_charging_sessions(
            args.wallbox_id, now - timedelta(days=30), now
        )
        print(f"Charging sessions (last 30 days): {len(sessions)}")
        for charging_session in sessions:
            end = charging_session.end.isoformat() if charging_session.end else "OPEN"
            print(
                f"  - {charging_session.start.isoformat()} -> {end}: "
                f"{charging_session.charged_energy} kWh"
            )
        print("\nAll smoke checks passed — this wallbox ID is the one to configure.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
