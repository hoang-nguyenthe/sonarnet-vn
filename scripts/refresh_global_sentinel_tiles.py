#!/usr/bin/env python3
"""Create a timestamped, multi-pass Sentinel-1 mosaic for global sea corridors."""
from __future__ import annotations

import json
import os
import sys
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sonarnet.data.copernicus import access_token, search_sentinel1_grd, sentinel1_mosaic_preview

# A globe-scale maritime mosaic needs multiple swaths; every swath is retained
# with its own acquisition time instead of pretending all pixels are synchronous.
TILES = {
    "sea_of_japan": (123.0, 33.0, 131.0, 41.0),
    "southeast_asia": (103.0, 3.0, 111.0, 11.0),
    "indian_ocean": (54.0, 16.0, 62.0, 24.0),
    "mediterranean_suez": (27.0, 28.0, 35.0, 36.0),
    "north_sea_atlantic": (-4.0, 50.0, 4.0, 58.0),
    "east_america": (-82.0, 25.0, -74.0, 33.0),
    "west_america": (-123.0, 30.0, -115.0, 38.0),
    "southern_africa": (15.0, -35.0, 23.0, -27.0),
}
LABELS = {
    "sea_of_japan": "Tây Thái Bình Dương", "southeast_asia": "Đông Nam Á", "indian_ocean": "Ấn Độ Dương",
    "mediterranean_suez": "Địa Trung Hải – Suez", "north_sea_atlantic": "Đại Tây Dương châu Âu",
    "east_america": "Bờ đông châu Mỹ", "west_america": "Bờ tây châu Mỹ", "southern_africa": "Nam Phi",
}
ASSET_DIR = ROOT / "assets" / "sentinel1_global"


def credentials() -> tuple[str, str]:
    if os.getenv("COPERNICUS_CLIENT_ID") and os.getenv("COPERNICUS_CLIENT_SECRET"):
        return os.environ["COPERNICUS_CLIENT_ID"], os.environ["COPERNICUS_CLIENT_SECRET"]
    with (ROOT / ".streamlit" / "secrets.toml").open("rb") as source:
        values = tomllib.load(source)["copernicus"]
    return values["client_id"], values["client_secret"]


def main() -> None:
    client_id, client_secret = credentials()
    token, end = access_token(client_id, client_secret), date.today()
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for key, bbox in TILES.items():
        try:
            products = search_sentinel1_grd(token, bbox, end - timedelta(days=14), end, limit=50)
            newest = max(products, key=lambda product: product.acquired_at) if products else None
            image = sentinel1_mosaic_preview(token, bbox, end - timedelta(days=14), end, width=720)
        except Exception as exc:  # Keep the previously verified tile, if any.
            print(f"Keeping previous {key}: {exc}")
            continue
        output = ASSET_DIR / f"{key}.png"
        output.write_bytes(image)
        records.append({
            "key": key, "label": LABELS[key], "bbox": bbox, "asset": f"sentinel1_global/{key}.png",
            "newest_catalog_acquired_at": newest.acquired_at if newest else None,
            "catalog_scene_count": len(products), "window_start": (end - timedelta(days=14)).isoformat(), "window_end": end.isoformat(),
        })
        print(f"Prepared {key}: {len(image):,} bytes")
    (ASSET_DIR / "latest.json").write_text(json.dumps({
        "source": "Copernicus Data Space · Sentinel-1 GRD", "refreshed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tiles": records, "note": "Mỗi tile là mosaic Sentinel-1 theo pixel mới nhất trong cửa sổ 14 ngày; thời điểm khác nhau theo vùng.",
    }, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
