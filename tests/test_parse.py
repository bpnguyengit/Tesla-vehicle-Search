#!/usr/bin/env python3
"""Unit checks for inventory parsing (no network)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inventory import (  # noqa: E402
    GeoPoint,
    _flatten_results,
    parse_vehicle,
    search_inventory,
    year_in_range,
)


class ParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name("fixture_inventory.json")
        cls.payload = json.loads(path.read_text())

    def test_flatten_list(self):
        rows = _flatten_results(self.payload)
        self.assertEqual(len(rows), 2)

    def test_flatten_buckets(self):
        payload = {
            "results": {"exact": [self.payload["results"][0]], "approximate": [], "approximateOutside": []},
            "total_matches_found": 1,
        }
        self.assertEqual(len(_flatten_results(payload)), 1)

    def test_parse_used_with_distance(self):
        origin = GeoPoint(lat=34.0901, lng=-118.4065, zip_code="90210")
        v = parse_vehicle(self.payload["results"][0], condition="used", origin=origin)
        self.assertEqual(v.model_name, "Model Y")
        self.assertEqual(v.price, 26300)
        self.assertEqual(v.location, "Owings Mills, MD")
        self.assertIsNotNone(v.distance_miles)
        self.assertGreater(v.distance_miles, 2000)  # MD from Beverly Hills

    def test_discount_from_field(self):
        v = parse_vehicle(self.payload["results"][1], condition="new")
        self.assertEqual(v.price, 48500)
        self.assertEqual(v.discount, 990)
        self.assertEqual(v.location, "Location TBA")

    def test_year_filter(self):
        self.assertTrue(year_in_range(None, 2018, 2026, filter_active=False))
        self.assertFalse(year_in_range(None, 2020, 2024, filter_active=True))
        self.assertTrue(year_in_range(2022, 2020, 2024, filter_active=True))
        self.assertFalse(year_in_range(2019, 2020, 2024, filter_active=True))

    def test_search_with_injected_fetch(self):
        calls = {"n": 0}

        def fake_fetch(query_obj):
            calls["n"] += 1
            # Only return data for first call; empty after to stop paging.
            if query_obj["offset"] == 0 and query_obj["query"]["condition"] == "used":
                return self.payload
            return {"results": [], "total_matches_found": 0}

        geo = GeoPoint(lat=34.0901, lng=-118.4065, zip_code="90210")
        result = search_inventory(
            models=["Model Y"],
            condition="used",
            zip_code="90210",
            max_miles=None,
            year_min=2018,
            year_max=2030,
            year_filter_active=False,
            geo=geo,
            fetch_page_fn=fake_fetch,
            page_delay=0,
        )
        self.assertGreaterEqual(calls["n"], 1)
        self.assertEqual(len(result.vehicles), 2)
        self.assertTrue(result.vehicles[0].is_best_deal)
        self.assertEqual(result.vehicles[0].price, 26300)


if __name__ == "__main__":
    unittest.main()
