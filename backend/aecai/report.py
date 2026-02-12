"""Report generation – produces per-floor fixture counts and building totals.

Takes the raw per-page fixture recognition results and aggregates them into
structured data suitable for JSON API responses and TXT report download.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def count_fixtures_per_floor(
    page_results: dict[str, list[dict]],
) -> dict[str, Counter]:
    """Aggregate fixture counts per floor.

    Args:
        page_results: mapping of floor_name → list of recognition dicts
                      (each dict has "fixture" key, None if unrecognised)

    Returns:
        mapping of floor_name → Counter of fixture codes
    """
    floor_counts: dict[str, Counter] = {}
    for floor_name, detections in page_results.items():
        counter: Counter = Counter()
        for det in detections:
            code = det.get("fixture")
            if code:
                counter[code] += 1
        if counter:
            floor_counts[floor_name] = counter
    return floor_counts


def compute_building_totals(
    floor_counts: dict[str, Counter],
    multipliers: dict[str, int] | None = None,
) -> Counter:
    """Sum fixture counts across all floors, applying typical-floor multipliers."""
    multipliers = multipliers or {}
    totals: Counter = Counter()
    for floor_name, counts in floor_counts.items():
        mult = multipliers.get(floor_name, 1)
        for code, qty in counts.items():
            totals[code] += qty * mult
    return totals


def build_results_json(
    floor_counts: dict[str, Counter],
    multipliers: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build the full JSON results payload.

    Returns:
        {
            "floors": { "Level 2": { "LT04": 18, ... }, ... },
            "building_totals": { "LT04": 54, ... },
            "summary": {
                "total_fixtures": 342,
                "num_floors": 7,
                "luminaire_types": ["LT04", "LT04A", ...]
            }
        }
    """
    building_totals = compute_building_totals(floor_counts, multipliers)

    # Collect all unique luminaire types across all floors
    all_types: set[str] = set()
    floors_dict: dict[str, dict[str, int]] = {}
    for floor_name, counts in floor_counts.items():
        floors_dict[floor_name] = dict(counts)
        all_types.update(counts.keys())

    sorted_types = sorted(all_types)

    return {
        "floors": floors_dict,
        "building_totals": dict(building_totals),
        "summary": {
            "total_fixtures": sum(building_totals.values()),
            "num_floors": len(floor_counts),
            "luminaire_types": sorted_types,
        },
    }


def generate_txt_report(
    floor_counts: dict[str, Counter],
    multipliers: dict[str, int] | None = None,
) -> str:
    """Generate the plain-text report matching the original CLI output format.

    Produces TABLE 1 (per-floor counts) and building totals.
    """
    building_totals = compute_building_totals(floor_counts, multipliers)
    multipliers = multipliers or {}

    all_types = sorted({code for c in floor_counts.values() for code in c})
    if not all_types:
        return "No fixtures detected.\n"

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("AECAI – Automated Lighting Fixture Takeoff Report")
    lines.append("=" * 72)
    lines.append("")

    # TABLE 1: Per-floor breakdown
    lines.append("TABLE 1: Fixture Count by Floor")
    lines.append("-" * 72)

    # Header row
    header = f"{'Floor':<20}" + "".join(f"{t:>8}" for t in all_types) + f"{'Total':>10}"
    lines.append(header)
    lines.append("-" * len(header))

    for floor_name, counts in floor_counts.items():
        mult = multipliers.get(floor_name, 1)
        mult_str = f" (x{mult})" if mult > 1 else ""
        row = f"{floor_name + mult_str:<20}"
        floor_total = 0
        for t in all_types:
            qty = counts.get(t, 0)
            row += f"{qty:>8}"
            floor_total += qty
        row += f"{floor_total:>10}"
        lines.append(row)

    # Totals row
    lines.append("-" * len(header))
    totals_row = f"{'BUILDING TOTAL':<20}"
    grand_total = 0
    for t in all_types:
        qty = building_totals.get(t, 0)
        totals_row += f"{qty:>8}"
        grand_total += qty
    totals_row += f"{grand_total:>10}"
    lines.append(totals_row)
    lines.append("=" * len(header))
    lines.append("")

    return "\n".join(lines)
