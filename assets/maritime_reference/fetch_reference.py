"""Refresh an attributed, non-legal Vietnam maritime reference from VLIZ.

Run manually with Python 3. Only this directory is written. No credentials.
The source's calculated/undelimited line classifications are preserved.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.geometry import shape
from shapely.validation import explain_validity

ROOT = Path(__file__).resolve().parent
ENDPOINT = 'https://geo.vliz.be/geoserver/MarineRegions/wfs'


def fetch(layer, condition):
    url = ENDPOINT + '?' + urlencode({
        'service': 'WFS', 'version': '1.0.0', 'request': 'GetFeature',
        'typeName': layer, 'cql_filter': condition,
        'srsName': 'EPSG:4326', 'outputFormat': 'application/json',
    })
    with urlopen(Request(url, headers={'User-Agent': 'SonarNet-VN maritime reference/1.0'}), timeout=60) as response:
        raw = response.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError('Unexpected reference size; refusing publication')
    data = json.loads(raw)
    if data.get('type') != 'FeatureCollection' or not data.get('features'):
        raise ValueError('Empty or invalid source response')
    return url, raw, data


def positions(coordinates):
    if coordinates and isinstance(coordinates[0], (float, int)):
        yield coordinates
    else:
        for member in coordinates:
            yield from positions(member)


def validate(data):
    bounds = [180., 90., -180., -90.]
    count = 0
    geometry_checks = []
    for feature in data['features']:
        geometry = feature['geometry']
        if geometry['type'] not in {'Polygon', 'MultiPolygon', 'LineString', 'MultiLineString'}:
            raise ValueError('Unexpected geometry type')
        for coordinate in positions(geometry['coordinates']):
            lon, lat = coordinate[:2]
            if not 100 < lon < 119 or not 4 < lat < 24:
                raise ValueError('Unexpected Vietnam coordinates or reversed axis order')
            bounds = [min(bounds[0], lon), min(bounds[1], lat),
                      max(bounds[2], lon), max(bounds[3], lat)]
            count += 1
        parsed = shape(geometry)
        geometry_checks.append({'id': feature.get('id'), 'valid': bool(parsed.is_valid),
                                'empty': bool(parsed.is_empty), 'explanation': explain_validity(parsed)})
    return {'bbox_wgs84': bounds, 'coordinate_count': count,
            'geometry_checks': geometry_checks,
            'all_geometries_valid': all(item['valid'] and not item['empty'] for item in geometry_checks)}


def main():
    polygon_url, polygon_raw, polygon = fetch('eez', 'mrgid=8484')
    if len(polygon['features']) != 1 or polygon['features'][0]['properties'].get('mrgid') != 8484:
        raise ValueError('Incorrect reference feature')
    line_url, line_raw, lines = fetch('eez_boundaries', 'mrgid_eez1=8484 OR mrgid_eez2=8484')
    polygon_validation = validate(polygon)
    line_validation = validate(lines)
    if not line_validation['all_geometries_valid']:
        raise ValueError('Invalid boundary lines; refusing publication')
    metadata = {
        'title': 'Vùng biển tham khảo quanh Việt Nam',
        'dataset': 'Maritime Boundaries and Exclusive Economic Zones (200NM), version 12',
        'publisher': 'Flanders Marine Institute (VLIZ)',
        'edition_date': '2023-10-25',
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'doi': 'https://doi.org/10.14284/632',
        'source': 'https://www.marineregions.org/gazetteer.php?p=details&id=8484',
        'methodology': 'https://www.marineregions.org/eezmethodology.php',
        'line_types_source': 'https://www.marineregions.org/eezlinetype.php',
        'license': 'CC BY 4.0',
        'license_url': 'https://creativecommons.org/licenses/by/4.0/',
        'terms_url': 'https://www.marineregions.org/disclaimer.php',
        'attribution': 'Flanders Marine Institute (2023). Maritime Boundaries Geodatabase: Maritime Boundaries and Exclusive Economic Zones (200NM), version 12. https://doi.org/10.14284/632. CC BY 4.0.',
        'modifications': 'Selected Vietnam MRGID 8484 and its associated boundary lines from WFS. Source coordinates and attributes are unchanged.',
        'crs': 'EPSG:4326',
        'coordinate_order': 'longitude, latitude',
        'mrgid': 8484,
        'legal_boundary': False,
        'display_only': True,
        'recommended_display_file': 'vietnam_boundary_lines.geojson',
        'polygon_topology_note': 'The original WFS polygon is retained unchanged even if invalid; use valid source lines for display. Never use this polygon as a point-in-zone/legal geofence.',
        'recommended_label': 'Tham khảo biển Việt Nam · VLIZ v12',
        'disclaimer_vi': 'Lớp tham khảo nghiên cứu từ Marine Regions v12 (2023), không phải bản đồ pháp lý hoặc ranh giới chủ quyền. Gồm cả đường trung tuyến do nguồn tính toán; không dùng để kết luận tàu vi phạm hay dẫn đường.',
        'disputed_areas_vi': 'MRGID 8484 không biểu diễn đầy đủ mọi yêu sách biển hoặc chủ quyền đảo. Vùng yêu sách chồng lấn Biển Đông được nguồn lưu riêng (MRGID 49003), không được gộp vào lớp này hoặc quy về riêng một quốc gia.',
        'definition_note_vi': 'Theo phương pháp của VLIZ, polygon EEZ còn bao gồm nội thủy và lãnh hải; không đồng nhất với định nghĩa pháp lý riêng của vùng đặc quyền kinh tế.',
        'temporal_note_vi': 'Phiên bản dữ liệu 2023 không được coi là đã cập nhật các thay đổi pháp lý sau đó.',
        'legal_decision_use': 'Prohibited by application design: no geofence violation, citizenship, sovereignty, navigation, or enforcement inference from this reference.',
        'polygon': {'file': 'vietnam_eez.geojson', 'url': polygon_url,
                    'sha256': hashlib.sha256(polygon_raw).hexdigest(),
                    'feature_count': len(polygon['features']), **polygon_validation},
        'lines': {'file': 'vietnam_boundary_lines.geojson', 'url': line_url,
                  'sha256': hashlib.sha256(line_raw).hexdigest(),
                  'feature_count': len(lines['features']),
                  'line_types': dict(Counter(f['properties'].get('line_type') for f in lines['features'])),
                  **line_validation},
    }
    for name, data in [('vietnam_eez.geojson', polygon_raw), ('vietnam_boundary_lines.geojson', line_raw),
                       ('metadata.json', (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode())]:
        temporary = ROOT / (name + '.tmp')
        temporary.write_bytes(data)
        temporary.replace(ROOT / name)
    print(json.dumps({'polygon': metadata['polygon'], 'lines': metadata['lines']}, indent=2))


if __name__ == '__main__':
    main()
