"""Non-legal, attributed maritime reference; never a detection geofence."""
import json
from pathlib import Path
import folium


def add_reference(chart, root: Path):
    path = root / 'assets/maritime_reference/vietnam_boundary_lines.geojson'
    if not path.exists():
        return
    source = json.loads(path.read_text())
    features = [f for f in source['features'] if f['properties'].get('line_type') != 'Straight baseline']
    layer = folium.FeatureGroup(name='Phạm vi biển tham khảo', show=True).add_to(chart)
    for feature in features:
        folium.GeoJson(feature,
            style_function=lambda _: {'color': '#9cdef0', 'weight': 1.1, 'opacity': .85, 'dashArray': '5 6', 'fill': False},
            tooltip='Phạm vi biển tham khảo · không phải ranh giới pháp lý',
        ).add_child(folium.Popup(
            '<b>Phạm vi biển tham khảo quanh Việt Nam</b><br>'
            'Nguồn: Flanders Marine Institute (2023), Marine Regions v12. CC BY 4.0.<br>'
            'Gồm đường hiệp định, đường tính toán và đoạn chưa phân định. Không có giá trị pháp lý hoặc dẫn đường.<br>'
            '<a href="https://doi.org/10.14284/632" target="_blank" rel="noopener">Xem nguồn và phương pháp</a>',
            max_width=290)).add_to(layer)
