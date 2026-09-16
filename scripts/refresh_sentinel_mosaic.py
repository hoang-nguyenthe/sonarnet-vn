#!/usr/bin/env python3
"""Build the ready-to-display nationwide Sentinel-1 mosaic asset.

The script is designed for GitHub Actions: credentials are supplied through
COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET. For a local refresh it can
also read the developer's Streamlit secrets file, which is never committed.
"""
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

BBOX = (102.0, 6.0, 115.0, 21.8)
OUTPUT_IMAGE = ROOT / "assets" / "sentinel1_vietnam_latest.png"
OUTPUT_METADATA = ROOT / "assets" / "sentinel1_vietnam_latest.json"


def credentials() -> tuple[str, str]:
    client_id = os.getenv("COPERNICUS_CLIENT_ID")
    client_secret = os.getenv("COPERNICUS_CLIENT_SECRET")
    if client_id and client_secret:
        return client_id, client_secret
    with (ROOT / ".streamlit" / "secrets.toml").open("rb") as source:
        values = tomllib.load(source)["copernicus"]
    return values["client_id"], values["client_secret"]


def main() -> None:
    client_id, client_secret = credentials()
    today = date.today()
    token = access_token(client_id, client_secret)
    products = search_sentinel1_grd(token, BBOX, today - timedelta(days=14), today, limit=50)
    newest = max(products, key=lambda product: product.acquired_at) if products else None
    image = sentinel1_mosaic_preview(token, BBOX, today - timedelta(days=14), today)
    OUTPUT_IMAGE.write_bytes(image)
    OUTPUT_METADATA.write_text(json.dumps({
        "source": "Copernicus Data Space · Sentinel-1 GRD",
        "bbox": BBOX,
        "window_start": (today - timedelta(days=14)).isoformat(),
        "window_end": today.isoformat(),
        "catalog_scene_count": len(products),
        "newest_catalog_acquired_at": newest.acquired_at if newest else None,
        "refreshed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "rendering": "VV Gamma0 ellipsoid · most recent pixel mosaic",
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"Prepared {OUTPUT_IMAGE.name}: {len(image):,} bytes; {len(products)} catalog scenes")


if __name__ == "__main__":
    main()
