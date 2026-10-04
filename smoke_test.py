#!/usr/bin/env python3
"""
Headless smoke test of inventory search (no GUI).

Tries stdlib urllib first. If Tesla's edge returns 403 (common from
datacenter IPs), retries through a local Chrome session via nodriver when
available.
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from inventory import (  # noqa: E402
    PAGE_SIZE,
    InventoryError,
    _flatten_results,
    build_query,
    geocode_zip,
    parse_vehicle,
    search_inventory,
)


def _report(result) -> None:
    print(f"Vehicles: {len(result.vehicles)}")
    if getattr(result, "errors", None):
        print("Errors:", "; ".join(result.errors))
    if not result.vehicles:
        raise SystemExit("Smoke test failed: no priced vehicles returned.")
    best = result.vehicles[0]
    print("CHEAPEST:")
    print(
        f"  {best.model_name} | {best.trim} | year={best.year} | "
        f"price=${best.price:,.0f} | {best.location} | VIN={best.vin}"
    )
    if best.discount:
        print(f"  discount=${best.discount:,.0f}")
    print("SMOKE_OK")


def urllib_smoke() -> None:
    print("Geocoding 90210…")
    geo = geocode_zip("90210")
    print(f"  -> {geo.place_name}, {geo.state} ({geo.lat}, {geo.lng})")
    print("Searching Model Y / new via urllib…")
    result = search_inventory(
        models=["Model Y"],
        condition="new",
        zip_code="90210",
        max_miles=200,
        year_min=2012,
        year_max=2035,
        year_filter_active=False,
        per_query_cap=50,
        geo=geo,
        page_delay=0.25,
        progress=lambda m: print(f"  {m}"),
    )
    _report(result)


async def nodriver_smoke_async() -> None:
    try:
        import nodriver as uc
    except ImportError as exc:
        raise SystemExit(
            "urllib got HTTP 403 and nodriver is not installed. "
            "From a normal home/office network, `python3 smoke_test.py` "
            "should succeed with urllib alone."
        ) from exc

    print("Retrying live fetch via Chrome (nodriver)…")
    browser = await uc.start(headless=False)
    try:
        page = await browser.get("https://www.tesla.com/inventory/new/my")
        await asyncio.sleep(2.5)
        geo = geocode_zip("90210")

        async def browser_fetch(query_obj: dict) -> dict:
            encoded = urllib.parse.quote(json.dumps(query_obj, separators=(",", ":")))
            url = (
                "https://www.tesla.com/inventory/api/v4/inventory-results?query="
                + encoded
            )
            js = f"""
            (async () => {{
              const r = await fetch({json.dumps(url)}, {{
                headers: {{
                  'Accept': 'application/json, text/plain, */*',
                  'Referer': 'https://www.tesla.com/inventory/new/my'
                }}
              }});
              const t = await r.text();
              return JSON.stringify({{status: r.status, body: t}});
            }})()
            """
            raw = await page.evaluate(js, await_promise=True)
            payload = json.loads(raw)
            if payload["status"] != 200:
                raise InventoryError(
                    f"Browser fetch HTTP {payload['status']}",
                    status_code=payload["status"],
                )
            return json.loads(payload["body"])

        vehicles = []
        seen = set()
        offset = 0
        for _ in range(4):
            q = build_query(
                model_code="my",
                condition="new",
                geo=geo,
                range_miles=200,
                offset=offset,
                count=PAGE_SIZE,
                outside_search=True,
            )
            payload = await browser_fetch(q)
            page_rows = _flatten_results(payload)
            print(
                f"  page offset={offset} n={len(page_rows)} "
                f"total={payload.get('total_matches_found')}"
            )
            for raw in page_rows:
                v = parse_vehicle(raw, condition="new", origin=geo)
                if not v.vin or v.vin in seen or v.price is None:
                    continue
                seen.add(v.vin)
                vehicles.append(v)
            if len(page_rows) < PAGE_SIZE:
                break
            offset += len(page_rows)
            await asyncio.sleep(0.35)

        vehicles.sort(key=lambda v: v.price or 1e18)
        if vehicles:
            vehicles[0].raw["_best_deal"] = True
        result = SimpleNamespace(
            vehicles=vehicles,
            truncated=False,
            errors=[],
            queried=["Model Y (new)"],
        )
        _report(result)
    finally:
        try:
            browser.stop()
        except Exception:
            pass


def main() -> None:
    try:
        urllib_smoke()
        return
    except InventoryError as exc:
        print(f"urllib path failed: {exc}")
        if exc.status_code != 403:
            raise
    except SystemExit as exc:
        # _report exits when urllib returned zero vehicles after a soft failure.
        print(f"urllib smoke exited: {exc}")
    asyncio.run(nodriver_smoke_async())


if __name__ == "__main__":
    main()
