"""
Tesla public inventory API client (stdlib urllib).

Observed live (2026-10-03) via browser session against:
  GET https://www.tesla.com/inventory/api/v4/inventory-results?query=<url-encoded JSON>

Working query shape (US):
  {
    "query": {
      "model": "my",              # m3 | my | ms | mx | ct
      "condition": "new"|"used",
      "options": {},
      "arrangeby": "Price",
      "order": "asc",
      "market": "US",
      "language": "en",
      "super_region": "north america",
      "zip": "90210",
      "lat": 34.0901,
      "lng": -118.4065,
      "range": 200                 # miles; use large value + outsideSearch for nationwide
    },
    "offset": 0,
    "count": 50,
    "outsideOffset": 0,
    "outsideSearch": true         # needed to pull inventory beyond empty local buckets
  }

Response top-level: results, total_matches_found.
  results may be a list OR {"exact":[], "approximate":[], "approximateOutside":[]}.

Vehicle fields used (from live payloads):
  VIN, Model, TrimName, Year, Price, PurchasePrice, TotalPrice, InventoryPrice,
  Discount, Odometer, OdometerType, City, StateProvince, MetroName,
  TransportationFee, TitleStatus, PAINT, INTERIOR, OptionCodeList,
  CashDetails.cash.inventoryDiscountWithTax,
  vrlList[].lat/lon, geoPoints, CompositorViews / OptionCodeList (image build).

Effective buyer price: PurchasePrice, else InventoryPrice, else Price.
Discount shown: Discount field, else max(0, TotalPrice - PurchasePrice),
  else CashDetails inventoryDiscountWithTax.

Note: Tesla's Akamai edge may return HTTP 403 to datacenter / non-browser
TLS fingerprints. A normal desktop User-Agent is sent; if blocked, the error
is surfaced clearly. ZIP geocoding uses https://api.zippopotam.us/us/{zip}.
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

INVENTORY_URL = "https://www.tesla.com/inventory/api/v4/inventory-results"
ZIPPO_URL = "https://api.zippopotam.us/us/{zip}"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

MODEL_CODES = {
    "Model 3": "m3",
    "Model Y": "my",
    "Model S": "ms",
    "Model X": "mx",
    "Cybertruck": "ct",
}
CODE_TO_NAME = {v: k for k, v in MODEL_CODES.items()}

PAGE_SIZE = 50
# Cap per model×condition so nationwide searches stay polite.
DEFAULT_PER_QUERY_CAP = 200
REQUEST_TIMEOUT_SEC = 30
PAGE_DELAY_SEC = 0.35

ProgressCallback = Callable[[str], None]


class InventoryError(Exception):
    """Raised when Tesla inventory or geocoding fails in a user-visible way."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class GeoPoint:
    lat: float
    lng: float
    zip_code: str = ""
    place_name: str = ""
    state: str = ""


@dataclass
class Vehicle:
    vin: str
    model_code: str
    model_name: str
    trim: str
    year: Optional[int]
    price: Optional[float]  # effective / purchase price
    list_price: Optional[float]
    discount: Optional[float]
    odometer: Optional[float]
    odometer_unit: str
    city: str
    state: str
    location: str
    distance_miles: Optional[float]
    condition: str
    transportation_fee: Optional[float]
    paint: str
    interior: str
    option_codes: str
    title_status: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def is_best_deal(self) -> bool:
        return bool(self.raw.get("_best_deal"))


@dataclass
class SearchResult:
    vehicles: list[Vehicle]
    truncated: bool
    errors: list[str]
    queried: list[str]


def _http_get_json(url: str, timeout: float = REQUEST_TIMEOUT_SEC) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.tesla.com/inventory/new/my",
            "Origin": "https://www.tesla.com",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        if exc.code == 403:
            raise InventoryError(
                "Tesla blocked the request (HTTP 403). Their edge often rejects "
                "datacenter IPs or non-browser clients. Try again from a normal "
                "home/office network, or open tesla.com/inventory in a browser first.",
                status_code=403,
            ) from exc
        raise InventoryError(
            f"Tesla inventory HTTP {exc.code}: {detail or exc.reason}",
            status_code=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise InventoryError(f"Network error contacting Tesla inventory: {exc.reason}") from exc
    except TimeoutError as exc:
        raise InventoryError("Timed out waiting for Tesla inventory.") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise InventoryError(
            "Tesla inventory returned non-JSON (API schema may have changed). "
            f"Status {status}. Body starts: {body[:160]!r}"
        ) from exc


def geocode_zip(zip_code: str) -> GeoPoint:
    """Resolve a US ZIP to lat/lng via zippopotam.us (public, no key)."""
    zip_code = (zip_code or "").strip()
    if not zip_code.isdigit() or len(zip_code) != 5:
        raise InventoryError("Enter a valid 5-digit US ZIP code.")
    url = ZIPPO_URL.format(zip=zip_code)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise InventoryError(f"ZIP code {zip_code} was not found.") from exc
        raise InventoryError(f"Geocoder HTTP {exc.code}") from exc
    except Exception as exc:
        raise InventoryError(f"Could not geocode ZIP {zip_code}: {exc}") from exc

    places = data.get("places") or []
    if not places:
        raise InventoryError(f"No location found for ZIP {zip_code}.")
    place = places[0]
    return GeoPoint(
        lat=float(place["latitude"]),
        lng=float(place["longitude"]),
        zip_code=zip_code,
        place_name=place.get("place name") or "",
        state=place.get("state abbreviation") or "",
    )


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _flatten_results(payload: Any) -> list[dict]:
    results = payload.get("results") if isinstance(payload, dict) else None
    if results is None:
        return []
    if isinstance(results, list):
        return [r for r in results if isinstance(r, dict)]
    if isinstance(results, dict):
        out: list[dict] = []
        for key in ("exact", "approximate", "approximateOutside"):
            bucket = results.get(key) or []
            if isinstance(bucket, list):
                out.extend(r for r in bucket if isinstance(r, dict))
        # Also accept any other list-valued keys defensively.
        if not out:
            for value in results.values():
                if isinstance(value, list):
                    out.extend(r for r in value if isinstance(r, dict))
        return out
    return []


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    num = _to_float(value)
    if num is None:
        return None
    return int(num)


def _first_lat_lng(raw: dict) -> tuple[Optional[float], Optional[float]]:
    vrl = raw.get("vrlList") or []
    if isinstance(vrl, list) and vrl:
        item = vrl[0]
        if isinstance(item, dict):
            lat = _to_float(item.get("lat"))
            lng = _to_float(item.get("lon") if item.get("lon") is not None else item.get("lng"))
            if lat is not None and lng is not None and not (lat == 0 and lng == 0):
                return lat, lng
    geo = raw.get("geoPoints") or []
    if isinstance(geo, list) and geo:
        first = geo[0]
        # Observed: [["39.40,-76.75", 976], ...]
        if isinstance(first, list) and first:
            coord = first[0]
            if isinstance(coord, str) and "," in coord:
                a, b = coord.split(",", 1)
                lat, lng = _to_float(a), _to_float(b)
                if lat is not None and lng is not None and not (lat == 0 and lng == 0):
                    return lat, lng
    return None, None


def _effective_price(raw: dict) -> Optional[float]:
    for key in ("PurchasePrice", "InventoryPrice", "Price", "TotalPrice"):
        val = _to_float(raw.get(key))
        if val is not None and val > 0:
            return val
    return None


def _list_price(raw: dict) -> Optional[float]:
    for key in ("TotalPrice", "Price", "InventoryPrice"):
        val = _to_float(raw.get(key))
        if val is not None and val > 0:
            return val
    return None


def _discount_amount(raw: dict, purchase: Optional[float], listed: Optional[float]) -> Optional[float]:
    disc = _to_float(raw.get("Discount"))
    if disc is not None and disc > 0:
        return disc
    total_disc = _to_float(raw.get("TotalDiscount"))
    if total_disc is not None and total_disc > 0:
        return total_disc
    cash = ((raw.get("CashDetails") or {}).get("cash") or {})
    cash_disc = _to_float(cash.get("inventoryDiscountWithTax"))
    if cash_disc is not None and cash_disc > 0:
        return cash_disc
    if purchase is not None and listed is not None and listed > purchase:
        return listed - purchase
    return disc if disc is not None else None


def parse_vehicle(raw: dict, condition: str, origin: Optional[GeoPoint] = None) -> Vehicle:
    model_code = (raw.get("Model") or "").lower().strip()
    model_name = CODE_TO_NAME.get(model_code, model_code.upper() or "Unknown")
    purchase = _effective_price(raw)
    listed = _list_price(raw)
    discount = _discount_amount(raw, purchase, listed)
    city = (raw.get("City") or "").strip()
    state = (raw.get("StateProvince") or "").strip()
    metro = (raw.get("MetroName") or "").strip()
    if city and state:
        location = f"{city}, {state}"
    elif metro:
        location = metro
    elif city or state:
        location = city or state
    else:
        location = "Location TBA"

    lat, lng = _first_lat_lng(raw)
    distance = None
    if origin is not None and lat is not None and lng is not None:
        distance = round(haversine_miles(origin.lat, origin.lng, lat, lng), 1)

    paint = ""
    if isinstance(raw.get("PAINT"), list) and raw["PAINT"]:
        paint = str(raw["PAINT"][0]).replace("_", " ").title()
    interior = ""
    if isinstance(raw.get("INTERIOR"), list) and raw["INTERIOR"]:
        interior = str(raw["INTERIOR"][0]).replace("_", " ").title()

    return Vehicle(
        vin=str(raw.get("VIN") or ""),
        model_code=model_code,
        model_name=model_name,
        trim=str(raw.get("TrimName") or raw.get("TrimCode") or "").strip(),
        year=_to_int(raw.get("Year")),
        price=purchase,
        list_price=listed,
        discount=discount,
        odometer=_to_float(raw.get("Odometer")),
        odometer_unit=str(raw.get("OdometerTypeShort") or raw.get("OdometerType") or "mi"),
        city=city,
        state=state,
        location=location,
        distance_miles=distance,
        condition=condition,
        transportation_fee=_to_float(raw.get("TransportationFee")),
        paint=paint,
        interior=interior,
        option_codes=str(raw.get("OptionCodeList") or ""),
        title_status=str(raw.get("TitleStatus") or condition).upper(),
        lat=lat,
        lng=lng,
        raw=raw,
    )


def build_query(
    *,
    model_code: str,
    condition: str,
    geo: GeoPoint,
    range_miles: Optional[int],
    offset: int = 0,
    count: int = PAGE_SIZE,
    outside_search: bool = False,
) -> dict:
    q: dict[str, Any] = {
        "query": {
            "model": model_code,
            "condition": condition,
            "options": {},
            "arrangeby": "Price",
            "order": "asc",
            "market": "US",
            "language": "en",
            "super_region": "north america",
            "zip": geo.zip_code,
            "lat": geo.lat,
            "lng": geo.lng,
            "range": int(range_miles) if range_miles is not None else 5000,
        },
        "offset": int(offset),
        "count": int(count),
        "outsideOffset": 0,
        "outsideSearch": bool(outside_search),
    }
    return q


def fetch_page(query_obj: dict) -> dict:
    encoded = urllib.parse.quote(json.dumps(query_obj, separators=(",", ":")))
    url = f"{INVENTORY_URL}?query={encoded}"
    payload = _http_get_json(url)
    if not isinstance(payload, dict):
        raise InventoryError("Unexpected inventory payload type (expected JSON object).")
    return payload


def year_in_range(year: Optional[int], year_min: int, year_max: int, filter_active: bool) -> bool:
    """
    Keep vehicles with missing Year when the year filter is wide open.
    If the user narrowed the range, drop missing / out-of-range years.
    """
    if not filter_active:
        return True
    if year is None:
        return False
    return year_min <= year <= year_max


def search_inventory(
    *,
    models: Iterable[str],
    condition: str = "both",  # new | used | both
    zip_code: str = "90210",
    max_miles: Optional[int] = None,  # None => nationwide
    year_min: int = 2012,
    year_max: int = 2030,
    year_filter_active: bool = False,
    per_query_cap: int = DEFAULT_PER_QUERY_CAP,
    page_delay: float = PAGE_DELAY_SEC,
    progress: Optional[ProgressCallback] = None,
    geo: Optional[GeoPoint] = None,
    fetch_page_fn: Callable[[dict], dict] = fetch_page,
) -> SearchResult:
    """
    Query Tesla inventory for the selected models/conditions and rank by price.

    fetch_page_fn is injectable for tests / alternate transports.
    """
    def say(msg: str) -> None:
        if progress:
            progress(msg)

    if geo is None:
        say(f"Geocoding ZIP {zip_code}…")
        geo = geocode_zip(zip_code)

    model_codes: list[str] = []
    for m in models:
        code = MODEL_CODES.get(m, m)
        code = code.lower().strip()
        if code in CODE_TO_NAME and code not in model_codes:
            model_codes.append(code)
    if not model_codes:
        raise InventoryError("Select at least one model.")

    conditions: list[str]
    c = (condition or "both").lower()
    if c == "both":
        conditions = ["new", "used"]
    elif c in ("new", "used"):
        conditions = [c]
    else:
        raise InventoryError("Condition must be New, Used, or Both.")

    nationwide = max_miles is None
    range_miles = 5000 if nationwide else int(max_miles)
    outside = True if nationwide else True  # outsideSearch helps when local buckets are empty
    # For tight local searches still set outsideSearch; Tesla returns outside matches
    # in approximateOutside when useful. User distance filter applied client-side too.

    vehicles: list[Vehicle] = []
    seen_vins: set[str] = set()
    errors: list[str] = []
    queried: list[str] = []
    truncated = False

    for model_code in model_codes:
        for cond in conditions:
            label = f"{CODE_TO_NAME.get(model_code, model_code)} ({cond})"
            queried.append(label)
            say(f"Searching {label}…")
            offset = 0
            gathered = 0
            try:
                while gathered < per_query_cap:
                    query_obj = build_query(
                        model_code=model_code,
                        condition=cond,
                        geo=geo,
                        range_miles=range_miles,
                        offset=offset,
                        count=min(PAGE_SIZE, per_query_cap - gathered),
                        outside_search=outside,
                    )
                    payload = fetch_page_fn(query_obj)
                    page = _flatten_results(payload)
                    total_raw = payload.get("total_matches_found")
                    try:
                        total_matches = int(total_raw) if total_raw is not None else None
                    except (TypeError, ValueError):
                        total_matches = None

                    if not page:
                        break

                    for raw in page:
                        vehicle = parse_vehicle(raw, condition=cond, origin=geo)
                        if vehicle.vin and vehicle.vin in seen_vins:
                            continue
                        if vehicle.vin:
                            seen_vins.add(vehicle.vin)
                        if vehicle.price is None:
                            continue
                        if not year_in_range(vehicle.year, year_min, year_max, year_filter_active):
                            continue
                        if not nationwide and vehicle.distance_miles is not None:
                            if vehicle.distance_miles > range_miles:
                                continue
                        vehicles.append(vehicle)
                        gathered += 1
                        if gathered >= per_query_cap:
                            break

                    offset += len(page)
                    if len(page) < PAGE_SIZE:
                        break
                    if total_matches is not None and offset >= total_matches:
                        break
                    if gathered >= per_query_cap:
                        if total_matches is not None and total_matches > per_query_cap:
                            truncated = True
                        elif total_matches is None:
                            truncated = True
                        break
                    time.sleep(page_delay)
            except InventoryError as exc:
                errors.append(f"{label}: {exc}")
                say(str(exc))
                # Abort hard on 403 — further calls will fail the same way.
                if exc.status_code == 403:
                    raise

    vehicles.sort(key=lambda v: (v.price is None, v.price if v.price is not None else 1e18))
    if vehicles:
        vehicles[0].raw["_best_deal"] = True

    say(f"Done. {len(vehicles)} matching vehicle(s).")
    return SearchResult(
        vehicles=vehicles,
        truncated=truncated,
        errors=errors,
        queried=queried,
    )


def mark_best_deals(vehicles: list[Vehicle]) -> list[Vehicle]:
    """Ensure cheapest priced vehicle is flagged (idempotent)."""
    priced = [v for v in vehicles if v.price is not None]
    if not priced:
        return vehicles
    best = min(priced, key=lambda v: v.price)  # type: ignore[arg-type, return-value]
    for v in vehicles:
        v.raw.pop("_best_deal", None)
    best.raw["_best_deal"] = True
    return vehicles
