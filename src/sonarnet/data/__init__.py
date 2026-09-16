"""Lớp dữ liệu: mô phỏng cảnh ảnh radar, dòng AIS và quỹ đạo phương tiện."""

from .dataset import build_dataset, load_image, read_ais, read_scene_meta  # noqa: F401
from .geo import SceneGeoReference, haversine_m  # noqa: F401
from .sar_render import SARRenderer, ShipFootprint  # noqa: F401
from .simulator import AIS_MISMATCH, AIS_OK, DARK, Scene, SceneSimulator, Vessel  # noqa: F401
from .tracks import Track, generate_track, generate_track_dataset  # noqa: F401
