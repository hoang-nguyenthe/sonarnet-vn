"""Display EPSG:4326 Sentinel rasters on Leaflet's EPSG:3857 map.

Only display pixels are warped. Detector inputs, coordinates and evidence
hashes remain in their original geographic raster grid.
"""
import base64
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import numpy as np
from PIL import Image
from folium.utilities import mercator_transform


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
