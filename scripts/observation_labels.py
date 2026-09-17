"""Readable location/date labels without inventing a vessel or locality."""
from datetime import date


def coordinates(latitude, longitude):
    return f"{abs(latitude):.3f}°{'B' if latitude >= 0 else 'N'}, {abs(longitude):.3f}°{'Đ' if longitude >= 0 else 'T'}"


def day_label(value):
    return date.fromisoformat(value).strftime('%d/%m/%Y')


def candidate_label(candidate, number):
    return f"Điểm {number} · {coordinates(candidate['latitude'], candidate['longitude'])} · {day_label(candidate['observation_day_utc'])}"


def tile_label(tile):
    west, south, east, north = tile['bbox']
    return f"{coordinates((south+north)/2, (west+east)/2)} · {day_label(tile['observation_day_utc'])} · {len(tile['detections'])} điểm"
