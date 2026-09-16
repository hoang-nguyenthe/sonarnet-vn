"""SonarNet-VN — Hệ thống giám sát tuân thủ quy định chống khai thác IUU.

Hợp nhất ảnh vệ tinh radar khẩu độ tổng hợp với tín hiệu giám sát hành trình
để phát hiện phương tiện khai thác thuỷ sản mất kết nối thiết bị, phục vụ công
tác gỡ cảnh báo thẻ vàng của Uỷ ban châu Âu và bảo vệ sinh kế ngư dân.
"""

__version__ = "1.0.0"

from .config import CFG, RunConfig, describe  # noqa: F401
from .utils import get_logger, probe_devices, set_seed, timed  # noqa: F401

__all__ = [
    "CFG",
    "RunConfig",
    "describe",
    "get_logger",
    "probe_devices",
    "set_seed",
    "timed",
    "__version__",
]
