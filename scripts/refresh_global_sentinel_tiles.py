#!/usr/bin/env python3
"""Create a timestamped, multi-pass Sentinel-1 mosaic for global sea corridors."""
from __future__ import annotations

import json
from io import BytesIO
from PIL import Image
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
# The grid is intentionally coarse enough for a scheduled public refresh while
# still giving the viewer worldwide context.  Empty/unavailable cells are
# omitted rather than painted with invented data.
TILES = {
    "north_pacific": (-154.0, 54.0, -146.0, 62.0),
    "central_pacific": (-160.0, 17.0, -152.0, 25.0),
    "south_pacific": (170.0, -42.0, 178.0, -34.0),
    "north_atlantic": (-65.0, 42.0, -57.0, 50.0),
    "tropical_atlantic": (-43.0, -7.0, -35.0, 1.0),
    "south_atlantic": (-55.0, -36.0, -47.0, -28.0),
    "caribbean_gulf": (-94.0, 22.0, -86.0, 30.0),
    "north_sea_atlantic": (-4.0, 50.0, 4.0, 58.0),
    "mediterranean_suez": (27.0, 28.0, 35.0, 36.0),
    "west_africa": (-20.0, 10.0, -12.0, 18.0),
    "east_america": (-82.0, 25.0, -74.0, 33.0),
    "west_america": (-123.0, 30.0, -115.0, 38.0),
    "arabian_sea": (65.0, 17.0, 73.0, 25.0),
    "bay_bengal": (86.0, 15.0, 94.0, 23.0),
    "indian_ocean": (54.0, 16.0, 62.0, 24.0),
    "southeast_asia": (103.0, 3.0, 111.0, 11.0),
    "sea_of_japan": (123.0, 33.0, 131.0, 41.0),
    "east_asia": (134.0, 31.0, 142.0, 39.0),
    "western_pacific": (120.0, 5.0, 128.0, 13.0),
    "australia_east": (149.0, -35.0, 157.0, -27.0),
    "australia_west": (111.0, -35.0, 119.0, -27.0),
    "southern_africa": (15.0, -35.0, 23.0, -27.0),
}
LABELS = {
    "sea_of_japan": "Biển Hoa Đông – bán đảo Triều Tiên",
    "north_pacific": "Bắc Thái Bình Dương", "central_pacific": "Trung Thái Bình Dương", "south_pacific": "Nam Thái Bình Dương",
    "north_atlantic": "Bắc Đại Tây Dương", "tropical_atlantic": "Nhiệt đới Đại Tây Dương", "south_atlantic": "Nam Đại Tây Dương",
    "caribbean_gulf": "Caribe – Vịnh Mexico", "north_sea_atlantic": "Bắc Hải – Đại Tây Dương",
    "mediterranean_suez": "Địa Trung Hải – Suez", "west_africa": "Tây Phi",
    "east_america": "Bờ đông châu Mỹ", "west_america": "Bờ tây châu Mỹ", "arabian_sea": "Biển Ả Rập",
    "bay_bengal": "Vịnh Bengal", "indian_ocean": "Ấn Độ Dương", "southeast_asia": "Đông Nam Á",
    "east_asia": "Đông Á", "western_pacific": "Tây Thái Bình Dương", "australia_east": "Bờ đông Australia",
    "australia_west": "Bờ tây Australia", "southern_africa": "Nam Phi",
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
    previous_path = ASSET_DIR / "latest.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    previous_tiles = {
        item['key']: dict(item, refreshed_at=item.get('refreshed_at') or previous.get('refreshed_at'))
        for item in previous.get('tiles', [])
    }
    records = []
    successes = 0
    for key, bbox in TILES.items():
        try:
            products = search_sentinel1_grd(token, bbox, end - timedelta(days=14), end, limit=50)
            if not products:
                raise RuntimeError('Không có cảnh Sentinel-1 trong cửa sổ 14 ngày')
            newest = max(products, key=lambda product: product.acquired_at) if products else None
            image = sentinel1_mosaic_preview(token, bbox, end - timedelta(days=14), end, width=720)
            with Image.open(BytesIO(image)) as picture:
                picture.verify()
        except Exception as exc:  # Keep the previously verified tile, if any.
            print(f"Keeping previous {key}: {exc}")
            if key in previous_tiles:
                records.append(previous_tiles[key])
            continue
        output = ASSET_DIR / f"{key}.png"
        output.write_bytes(image)
        successes += 1
        records.append({
            "key": key, "label": LABELS[key], "bbox": bbox, "asset": f"sentinel1_global/{key}.png",
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "newest_catalog_acquired_at": newest.acquired_at if newest else None,
            "catalog_scene_count": len(products), "window_start": (end - timedelta(days=14)).isoformat(), "window_end": end.isoformat(),
        })
        print(f"Prepared {key}: {len(image):,} bytes")
    if not successes:
        raise RuntimeError("No new valid tiles; keeping the previous manifest unchanged")
    (ASSET_DIR / "latest.json").write_text(json.dumps({
        "source": "Copernicus Data Space · Sentinel-1 GRD", "refreshed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tiles": records, "note": "Mỗi tile là mosaic Sentinel-1 theo pixel mới nhất trong cửa sổ 14 ngày; thời điểm khác nhau theo vùng.",
    }, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
