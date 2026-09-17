"""Conservative, auditable maritime land exclusion, independent of map toggles."""
from functools import lru_cache
import json
import gzip
from PIL import Image, ImageDraw
from shapely.geometry import box, shape, mapping


@lru_cache(maxsize=4)
def load_mask(path, modified_ns):
    data = json.loads(gzip.decompress(path.read_bytes()))
    return data, {key: shape(value) for key, value in data['geometry'].items()}


def get_mask(root):
    path = root / 'assets/land_mask/vietnam.json.gz'
    return load_mask(path, path.stat().st_mtime_ns)


def classify(tile, candidate, data, geometries):
    w, s, e, n = tile['bbox']
    width, height = tile['image_size']
    x1, y1, x2, y2 = candidate['bbox_px']
    footprint = box(w+x1/width*(e-w), n-y2/height*(n-s),
                    w+x2/width*(e-w), n-y1/height*(n-s))
    if not box(*data['coverage_bbox']).covers(footprint):
        return 'unknown'
    if geometries['land'].intersects(footprint):
        return 'excluded_land'
    if geometries['coast'].intersects(footprint):
        return 'excluded_coast'
    return 'water'


def filter_tile(root, tile):
    """Preserve raw model output in the manifest; only active list is filtered."""
    try:
        data, geometries = get_mask(root)
    except (OSError, ValueError, KeyError):
        tile['land_mask_status'] = 'unavailable'
        for candidate in tile['detections']:
            candidate['surface'] = 'unknown'
        return
    tile['land_mask_version'] = data['version'] + '-exclude-coast-500m-v2'
    tile['land_mask_status'] = 'applied'
    tile['raw_detection_count'] = len(tile['detections'])
    kept, excluded = [], []
    for original in tile['detections']:
        candidate = dict(original, surface=classify(tile, original, data, geometries))
        (excluded if candidate['surface'].startswith('excluded_') else kept).append(candidate)
    tile['detections'], tile['excluded_detections'] = kept, excluded


def annotated_image(root, tile):
    """Render the same filtered candidates used in the map, lists and export."""
    with Image.open(root / tile['asset_dir'] / 'sar.png') as source:
        image = source.convert('RGB')
    draw = ImageDraw.Draw(image)
    for d in tile['detections']:
        color = '#ff9f0a' if d.get('surface') == 'near_coast' else '#64d2ff'
        draw.rectangle(d['bbox_px'], outline=color, width=2)
        draw.text((d['bbox_px'][0], max(0, d['bbox_px'][1]-12)), str(d['id']), fill=color)
    return image


def add_map_layer(chart, root):
    import folium
    try:
        data, geometries = get_mask(root)
    except (OSError, ValueError, KeyError):
        return
    layer = folium.FeatureGroup(name='Đất liền · loại trừ YOLO (Việt Nam)', show=True).add_to(chart)
    folium.GeoJson(mapping(geometries['land'].simplify(.0001, preserve_topology=True)),
        style_function=lambda _: {'color': '#919aa8', 'weight': .5, 'fillColor': '#64748b', 'fillOpacity': .22},
        tooltip='Vùng loại trừ trên đất · GSHHG 2.3.7 · không phải ranh giới hành chính',
        ).add_to(layer)
    coastal = folium.FeatureGroup(name='Ven bờ 500 m · loại trừ YOLO', show=True).add_to(chart)
    folium.GeoJson(mapping(geometries['coast'].simplify(.0001, preserve_topology=True)),
        style_function=lambda _: {'color': '#ff9f0a', 'weight': .7, 'fillColor': '#ff9f0a', 'fillOpacity': .25},
        tooltip='Vùng loại trừ: từ đường bờ ra biển 500 m · không hiển thị ứng viên YOLO/AIS minh hoạ',
        ).add_to(coastal)


def summary(tiles):
    excluded = sum(d.get('surface') == 'excluded_land' for t in tiles for d in t.get('excluded_detections', []))
    coastal = sum(d.get('surface') == 'excluded_coast' for t in tiles for d in t.get('excluded_detections', []))
    unknown = sum(d.get('surface') == 'unknown' for t in tiles for d in t['detections'])
    return (f'Vùng loại trừ YOLO: đất liền và 500 m từ bờ ra biển. Đã loại {excluded} ứng viên chạm đất, {coastal} ứng viên ven bờ. '
            f'{unknown} ứng viên chưa xác định loại bề mặt. Tàu trong cảng/sát bờ cũng bị bỏ qua; điểm còn lại chưa phải tàu đã xác minh.')
