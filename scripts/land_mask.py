"""Conservative, auditable maritime land exclusion, independent of map toggles."""
from functools import lru_cache
import json
import gzip
from PIL import Image, ImageDraw
from shapely.geometry import box, shape, mapping
from shapely import prepare


@lru_cache(maxsize=1)
def load_mask(path, modified_ns):
    data = json.loads(gzip.decompress(path.read_bytes()))
    # Retain native geometries, not a second tree of millions of Python
    # coordinate objects. Display geometry is separately retained below.
    source = data.pop('geometry')
    geometries = {key: shape(value) for key, value in source.items()}
    # Prepared polygons make repeated tile/bbox filtering inexpensive. This
    # changes neither the full-resolution boundaries nor their coordinates.
    for key in ('land', 'coast'):
        prepare(geometries[key])
    return data, geometries


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
    tile['land_mask_version'] = data['version']
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


def add_map_layer(chart, root, detail_bounds=None):
    import folium
    from branca.element import MacroElement, Template
    try:
        data, geometries = get_mask(root)
    except (OSError, ValueError, KeyError):
        return
    display = data.get('display', {})
    # Handle older manifests without showing their symmetric inland buffer.
    coastal_shape = display.get('coast') or mapping(
        geometries['coast'].difference(geometries['land']).simplify(.00005, preserve_topology=True))
    shoreline = display.get('shoreline') or mapping(geometries['shoreline'])
    if detail_bounds is not None:
        # Send only geometry around detector inputs, not 9 MB of coastline
        # for an entire country on every phone interaction. Filtering still
        # uses the full-resolution national mask, never this display subset.
        from shapely.ops import unary_union
        if not detail_bounds:
            return
        region = unary_union([box(*bounds).buffer(.02) for bounds in detail_bounds])
        coastal_shape = mapping(shape(coastal_shape).intersection(region))
        if shoreline:
            shoreline = mapping(shape(shoreline).intersection(region))
    layer = folium.FeatureGroup(name='Vùng bỏ qua sát bờ · 500 m', show=True)
    pane_name = 'coastal_exclusion_' + layer.get_name()
    folium.map.CustomPane(pane_name, z_index=410, pointer_events=False).add_to(chart)
    layer.add_to(chart)
    # No land tint and no strokes around thousands of islands: a translucent
    # sea-only ribbon appears when its 500 m width is meaningful on screen.
    folium.GeoJson(coastal_shape,
        style_function=lambda _: {'stroke': False, 'fillColor': '#c6ad7a', 'fillOpacity': .18},
        pane=pane_name, interactive=False,
        ).add_to(layer)
    if shoreline:
        folium.GeoJson(shoreline,
            style_function=lambda _: {'color': '#cbd5df', 'weight': .65, 'opacity': .5, 'fill': False},
            pane=pane_name, interactive=False,
            ).add_to(layer)
    visibility = MacroElement()
    visibility._template = Template("{% macro script(this, kwargs) %}" + f"""
        (function() {{
            const map = {chart.get_name()};
            const pane = map.getPane('{pane_name}');
            const update = () => {{ pane.style.display = map.getZoom() >= 9 ? '' : 'none'; }};
            update();
            map.on('zoomend', update);
        }})();
    """ + "{% endmacro %}")
    chart.add_child(visibility)


def summary(tiles):
    excluded = sum(d.get('surface') == 'excluded_land' for t in tiles for d in t.get('excluded_detections', []))
    coastal = sum(d.get('surface') == 'excluded_coast' for t in tiles for d in t.get('excluded_detections', []))
    unknown = sum(d.get('surface') == 'unknown' for t in tiles for d in t['detections'])
    return (f'Không xét mục tiêu trên đất liền và trong 500 m từ bờ ra biển. Đã bỏ qua {excluded} điểm chạm đất, {coastal} điểm sát bờ. '
            f'{unknown} ứng viên chưa xác định loại bề mặt. Tàu trong cảng/sát bờ cũng bị bỏ qua; điểm còn lại chưa phải tàu đã xác minh.')
