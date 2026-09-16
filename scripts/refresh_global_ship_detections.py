#!/usr/bin/env python3
"""Prepare a lightweight, real GFW SAR detection layer for the global map."""
from __future__ import annotations

import json
import os
import sys
import tomllib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sonarnet.data.gfw import GlobalFishingWatchError, sar_reference_report

# Maritime corridors provide global visual coverage while keeping the GFW
# report requests bounded and publishable within a scheduled workflow.
CORRIDORS = {
    "Đông Nam Á": (95.0, -10.0, 125.0, 20.0),
    "Tây Thái Bình Dương": (120.0, 20.0, 145.0, 48.0),
    "Ấn Độ Dương": (45.0, 5.0, 85.0, 28.0),
    "Địa Trung Hải – Suez": (10.0, 25.0, 45.0, 45.0),
    "Đại Tây Dương châu Âu": (-12.0, 35.0, 20.0, 60.0),
    "Bờ đông châu Mỹ": (-90.0, 10.0, -60.0, 45.0),
    "Bờ tây châu Mỹ": (-130.0, 20.0, -105.0, 50.0),
    "Nam Phi": (10.0, -35.0, 45.0, 5.0),
}
OUTPUT = ROOT / "assets" / "gfw_global_ship_detections_latest.json"


def token() -> str:
    if value := os.getenv("GFW_API_TOKEN"):
        return value
    with (ROOT / ".streamlit" / "secrets.toml").open("rb") as source:
        return tomllib.load(source)["gfw"]["api_token"]


def query(name: str, bbox: tuple[float, float, float, float], value: str, start: date, end: date):
    return name, sar_reference_report(value, bbox, start, end)


def main() -> None:
    end, start, value = date.today(), date.today() - timedelta(days=14), token()
    grouped: dict[tuple[float, float], dict] = defaultdict(lambda: {"detections": 0, "acquired_at": ""})
    succeeded: list[str] = []
    # GFW accepts one report at a time per token; sequential calls prevent
    # dropping valid global corridors with HTTP 429.
    for name, bbox in CORRIDORS.items():
        try:
            _, cells = query(name, bbox, value, start, end)
        except GlobalFishingWatchError as exc:
            print(f"Skipping {name}: {exc}")
            continue
        succeeded.append(name)
        for cell in cells:
            # Aggregate exact GFW cells into a 0.25° map-friendly grid.
            key = (round(cell.latitude * 4) / 4, round(cell.longitude * 4) / 4)
            aggregate = grouped[key]
            aggregate["detections"] += cell.detections
            aggregate["acquired_at"] = max(aggregate["acquired_at"], cell.acquired_at)
    points = [
        {"latitude": lat, "longitude": lon, **aggregate}
        for (lat, lon), aggregate in grouped.items()
    ]
    # A bounded asset keeps the interactive map responsive on phones.
    points.sort(key=lambda point: point["detections"], reverse=True)
    points = points[:1800]
    OUTPUT.write_text(json.dumps({
        "source": "Global Fishing Watch · public-global-sar-presence:latest",
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "refreshed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "corridors": succeeded, "points": points,
        "note": "Mỗi đốm là ô lưới phát hiện SAR đã gộp, không phải định danh một tàu.",
    }, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Prepared {len(points)} GFW SAR grid points from {len(succeeded)} corridors")


if __name__ == "__main__":
    main()
