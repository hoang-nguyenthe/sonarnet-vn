"""Display EPSG:4326 Sentinel rasters on Leaflet's EPSG:3857 map.

Only display pixels are warped. Detector inputs, coordinates and evidence
hashes remain in their original geographic raster grid.
"""
import base64
import hashlib
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import numpy as np
from PIL import Image
from folium.utilities import mercator_transform
from branca.element import MacroElement, Template


def project_rgba(image, south, north):
    rgba = np.asarray(image.convert('RGBA'), dtype=np.float64)
    # Premultiply colour by alpha before interpolation: no dark fringes around
    # a transparent/no-data scene edge when composing multiple radar images.
    rgba[:, :, :3] *= rgba[:, :, 3:4] / 255
    warped = mercator_transform(rgba, (south, north), origin='upper')
    alpha = warped[:, :, 3:4]
    warped[:, :, :3] = np.divide(warped[:, :, :3] * 255, alpha,
                                out=np.zeros_like(warped[:, :, :3]), where=alpha > 0)
    return Image.fromarray(np.rint(warped).clip(0, 255).astype('uint8'))


@lru_cache(maxsize=40)
def _projected_source(path, mtime_ns, south, north):
    with Image.open(path) as picture:
        result = project_rgba(picture, south, north)
    buffer = BytesIO()
    result.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()


def overlay_source(path, bbox):
    path = Path(path)
    return _projected_source(str(path), path.stat().st_mtime_ns, bbox[1], bbox[3])


def static_overlay_source(path, bbox, static_dir):
    """Cache display-only pixels outside the iframe; never expose source paths."""
    path = Path(path)
    identity = f'{path.resolve()}:{path.stat().st_mtime_ns}:{bbox}:mercator-v1'
    filename = hashlib.sha256(identity.encode()).hexdigest() + '.webp'
    directory = Path(static_dir) / 'radar'
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / filename
    if not destination.exists():
        prepared = path.with_name('map.webp')
        if prepared.exists():
            destination.write_bytes(prepared.read_bytes())
        else:
            with Image.open(path) as picture:
                result = project_rgba(picture, bbox[1], bbox[3])
            buffer = BytesIO()
            result.save(buffer, format='WEBP', lossless=True, method=0)
            destination.write_bytes(buffer.getvalue())
    # Relative to the app document: Cloud embeds it under /~/+/ while local
    # Streamlit runs at /. An origin-root URL bypasses Cloud's app router.
    return 'app/static/radar/' + filename


class ViewportRadar(MacroElement):
    """Load high-resolution imagery only after zooming into its footprint."""
    _template = Template('''
    {% macro script(this, kwargs) %}
    (function () {
        const map = {{ this.map_name }}, group = {{ this.group_name }};
        const records = {{ this.records | tojson }};
        const layers = new Map();
        function update() {
            const view = map.getBounds(), detailed = map.getZoom() >= 8;
            records.forEach(function (record, index) {
                const visible = detailed && view.intersects(record.bounds);
                if (visible && !layers.has(index)) {
                    const url = new URL(record.url, document.baseURI).href;
                    const layer = L.imageOverlay(url, record.bounds, {
                        opacity: 1, interactive: true, alt: record.label
                    }).bindPopup(record.popup);
                    layers.set(index, layer); group.addLayer(layer);
                } else if (!visible && layers.has(index)) {
                    group.removeLayer(layers.get(index)); layers.delete(index);
                }
            });
        }
        map.on('moveend zoomend', update); update();
    })();
    {% endmacro %}
    ''')

    def __init__(self, chart, group, records):
        super().__init__()
        self._name = 'ViewportRadar'
        self.map_name = chart.get_name()
        self.group_name = group.get_name()
        self.records = records
