"""Global Fishing Watch SAR reference client.

This module treats Global Fishing Watch SAR detections as an external reference
layer. It is never used to train SonarNet's detector or as absolute truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPORT_URL = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
SAR_DATASET = "public-global-sar-presence:latest"


class GlobalFishingWatchError(RuntimeError):
    """An API error that is safe to show in the dashboard."""


@dataclass(frozen=True)
class SarReferenceCell:
    """One aggregate GFW SAR cell, not a vessel identity."""

    acquired_at: str
    detections: int
    latitude: float
    longitude: float


def _bbox_geojson(bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    west, south, east, north = bbox
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": {
            "type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
        }}],
    }


def sar_reference_report(
    token: str, bbox: tuple[float, float, float, float], start: date, end: date, *, matched: bool | None = None,
) -> list[SarReferenceCell]:
    """Return gridded GFW SAR detections for a small region and time window."""
    params: list[tuple[str, str]] = [
        ("spatial-resolution", "HIGH"), ("temporal-resolution", "HOURLY"),
        ("datasets[0]", SAR_DATASET), ("date-range", f"{start.isoformat()},{end.isoformat()}"), ("format", "JSON"),
    ]
    if matched is not None:
        params.append(("filters[0]", f"matched='{str(matched).lower()}'"))
    request = Request(
        f"{REPORT_URL}?{urlencode(params)}", data=json.dumps({"geojson": _bbox_geojson(bbox)}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Cloudflare rejects urllib's default user agent. Keep a transparent,
            # contactable application identifier for API operators.
            "User-Agent": "SonarNet-VN/1.0 (academic research; contact: project-team)",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=100) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        messages = {401: "Global Fishing Watch từ chối token. Kiểm tra Streamlit secrets.", 429: "GFW đang xử lý một báo cáo khác. Thử lại sau."}
        detail = messages.get(exc.code, f"Global Fishing Watch trả về HTTP {exc.code}.")
        raise GlobalFishingWatchError(detail) from exc
    except URLError as exc:
        raise GlobalFishingWatchError("Không thể kết nối Global Fishing Watch. Kiểm tra mạng rồi thử lại.") from exc

    cells: list[SarReferenceCell] = []
    for entry in payload.get("entries", []):
        for values in entry.values():
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, dict) and "detections" in value:
                        cells.append(SarReferenceCell(
                            acquired_at=str(value.get("date", "Không rõ thời điểm")), detections=int(value["detections"]),
                            latitude=float(value.get("lat", 0.0)), longitude=float(value.get("lon", 0.0)),
                        ))
    return cells
