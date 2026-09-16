"""Small, dependency-free client for Copernicus Data Space Sentinel-1 GRD.

Credentials are deliberately passed in at runtime.  Store them in Streamlit
secrets or environment variables; never put them in source control.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOG_URL = "https://sh.dataspace.copernicus.eu/catalog/v1/search"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"


class CopernicusError(RuntimeError):
    """An API error that is safe to show in the dashboard."""


@dataclass(frozen=True)
class SentinelProduct:
    product_id: str
    acquired_at: str
    platform: str
    orbit: str
    polarization: str
    bbox: tuple[float, float, float, float]


def _request_json(url: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    # The Catalog service answers with a GeoJSON FeatureCollection.  Asking for
    # plain JSON alone currently produces HTTP 406 on the CDSE deployment.
    headers = {"Content-Type": "application/json", "Accept": "application/geo+json, application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise CopernicusError(f"Copernicus trả về HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise CopernicusError("Không thể kết nối Copernicus. Kiểm tra mạng rồi thử lại.") from exc


def access_token(client_id: str, client_secret: str) -> str:
    """Exchange the OAuth client credentials for a short-lived access token."""
    body = urlencode({"grant_type": "client_credentials", "client_id": client_id,
                      "client_secret": client_secret}).encode("utf-8")
    request = Request(TOKEN_URL, data=body,
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise CopernicusError("Copernicus từ chối OAuth. Kiểm tra client_id/client_secret.") from exc
    except URLError as exc:
        raise CopernicusError("Không thể kết nối Copernicus. Kiểm tra mạng rồi thử lại.") from exc
    token = payload.get("access_token")
    if not token:
        raise CopernicusError("Copernicus không trả về access token.")
    return str(token)


def search_sentinel1_grd(
    token: str, bbox: tuple[float, float, float, float], start: date, end: date, limit: int = 12
) -> list[SentinelProduct]:
    """Find recent Sentinel-1 GRD acquisitions intersecting a WGS84 bounding box."""
    start_iso = datetime.combine(start, time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    end_iso = datetime.combine(end, time.max, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    response = _request_json(CATALOG_URL, {
        "bbox": list(bbox), "datetime": f"{start_iso}/{end_iso}",
        "collections": ["sentinel-1-grd"], "limit": max(1, min(limit, 50)),
        "fields": {},
    }, token)
    products: list[SentinelProduct] = []
    for feature in response.get("features", []):
        props = feature.get("properties", {})
        raw_bbox = feature.get("bbox") or bbox
        products.append(SentinelProduct(
            product_id=str(feature.get("id", "Không rõ mã sản phẩm")),
            acquired_at=str(props.get("datetime") or props.get("start_datetime") or "Không rõ thời điểm"),
            platform=str(props.get("platform") or "Sentinel-1"),
            orbit=str(props.get("sat:orbit_state") or "Không rõ"),
            polarization=str(props.get("s1:polarization") or "Không rõ"),
            bbox=tuple(float(value) for value in raw_bbox),
        ))
    return products


def sentinel1_preview(
    token: str, bbox: tuple[float, float, float, float], acquired_at: str, width: int = 768
) -> bytes:
    """Render a VV backscatter preview as PNG for one calendar day of acquisition."""
    timestamp = acquired_at.replace("Z", "+00:00")
    day = datetime.fromisoformat(timestamp).date()
    start = datetime.combine(day, time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    end = datetime.combine(day, time.max, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    evalscript = """
//VERSION=3
function setup() {
  return { input: ["VV", "dataMask"], output: { bands: 4 } };
}
function evaluatePixel(sample) {
  var db = 10 * Math.log(sample.VV) / Math.LN10;
  var gray = Math.max(0, Math.min(1, (db + 25) / 30));
  return [gray, gray, gray, sample.dataMask];
}
"""
    height = max(256, min(1024, round(width * (bbox[3] - bbox[1]) / (bbox[2] - bbox[0]))))
    payload = {
        "input": {
            "bounds": {"bbox": list(bbox), "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [{
                "type": "sentinel-1-grd",
                "dataFilter": {"timeRange": {"from": start, "to": end}, "mosaickingOrder": "mostRecent"},
                # A nationwide mosaic spans many DEM tiles. Gamma0 ellipsoid
                # avoids intermittent CDSE DEM service failures; detailed
                # scene previews retain terrain correction in sentinel1_preview.
                "processing": {"backCoeff": "GAMMA0_ELLIPSOID"},
            }],
        },
        "output": {"width": width, "height": height,
                   "responses": [{"identifier": "default", "format": {"type": "image/png"}}]},
        "evalscript": evalscript,
    }
    request = Request(PROCESS_URL, data=json.dumps(payload).encode("utf-8"),
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=90) as response:
            image = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise CopernicusError(f"Không tạo được ảnh Sentinel-1 (HTTP {exc.code}): {detail}") from exc
    except URLError as exc:
        raise CopernicusError("Không thể tải ảnh Sentinel-1. Kiểm tra mạng rồi thử lại.") from exc
    if not image.startswith(b"\x89PNG"):
        raise CopernicusError("Copernicus không trả về ảnh PNG hợp lệ.")
    return image


def sentinel1_mosaic_preview(
    token: str, bbox: tuple[float, float, float, float], start: date, end: date, width: int = 1280,
) -> bytes:
    """Render a most-recent Sentinel-1 VV mosaic across a date window."""
    start_iso = datetime.combine(start, time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    end_iso = datetime.combine(end, time.max, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    evalscript = """
//VERSION=3
function setup() { return { input: ["VV", "dataMask"], output: { bands: 4 } }; }
function evaluatePixel(sample) {
  var db = 10 * Math.log(sample.VV) / Math.LN10;
  var gray = Math.max(0, Math.min(1, (db + 25) / 30));
  return [gray, gray, gray, sample.dataMask];
}
"""
    # S1GRD requires at least 1.5 km/pixel.  The full Vietnam bbox is tall,
    # so retain enough vertical pixels rather than capping it at 1024.
    height = max(256, min(1600, round(width * (bbox[3] - bbox[1]) / (bbox[2] - bbox[0]))))
    payload = {
        "input": {
            "bounds": {"bbox": list(bbox), "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [{
                "type": "sentinel-1-grd",
                "dataFilter": {"timeRange": {"from": start_iso, "to": end_iso}, "mosaickingOrder": "mostRecent"},
                "processing": {"orthorectify": True, "backCoeff": "GAMMA0_TERRAIN", "demInstance": "COPERNICUS_30"},
            }],
        },
        "output": {"width": width, "height": height, "responses": [{"identifier": "default", "format": {"type": "image/png"}}]},
        "evalscript": evalscript,
    }
    request = Request(PROCESS_URL, data=json.dumps(payload).encode("utf-8"),
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=120) as response:
            image = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise CopernicusError(f"Không tạo được mosaic Sentinel-1 (HTTP {exc.code}): {detail}") from exc
    except URLError as exc:
        raise CopernicusError("Không thể tải mosaic Sentinel-1. Kiểm tra mạng rồi thử lại.") from exc
    if not image.startswith(b"\x89PNG"):
        raise CopernicusError("Copernicus không trả về mosaic PNG hợp lệ.")
    return image
