"""Nội suy quỹ đạo AIS về đúng thời điểm chụp ảnh radar.

Bản ghi AIS được phát với nhịp không đều và kèm nhiễu vị trí. Để đối chiếu với
một cảnh ảnh radar chụp tại thời điểm ``T``, hệ thống cần ước lượng vị trí của
từng phương tiện đúng tại thời điểm đó.

Điểm mấu chốt về phương pháp
----------------------------
Thời điểm chụp ảnh nằm **ở giữa** chuỗi bản ghi AIS: hệ thống có cả quan trắc
trước lẫn quan trắc sau thời điểm đó. Vì vậy bài toán ở đây là *làm trơn*
(smoothing) chứ không phải *lọc* (filtering).

Một bộ lọc Kalman tiến thuần tuý chỉ khai thác quan trắc trong quá khứ rồi ngoại
suy tới thời điểm mục tiêu. Cách làm đó bỏ phí toàn bộ thông tin phía sau và để
sai số mô hình tích luỹ theo khoảng ngoại suy — trong thực nghiệm nó còn kém hơn
cả phép nội suy tuyến tính đơn giản.

Mô-đun này cài đặt bộ làm trơn **Rauch–Tung–Striebel**: chạy lọc tiến qua toàn
bộ chuỗi, sau đó chạy một lượt truy hồi ngược để phân bổ lại thông tin từ tương
lai về quá khứ. Kết quả là ước lượng tại thời điểm mục tiêu sử dụng **mọi** quan
trắc có được, đồng thời vẫn tôn trọng mô hình động học của phương tiện. Nhờ đó
nhiễu đo được trung bình hoá qua nhiều bản ghi thay vì truyền thẳng vào kết quả
như ở phép nội suy tuyến tính.

Vector trạng thái gồm bốn thành phần ``[đông, bắc, vận tốc đông, vận tốc bắc]``
tính theo mét trong hệ quy chiếu phẳng cục bộ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..data.geo import meters_per_degree

# Độ lệch chuẩn tiên nghiệm của vận tốc, tính theo mét trên giây.
# Giá trị 10 m/s tương ứng khoảng 20 hải lý trên giờ, bao phủ hầu hết
# phương tiện đánh bắt và vận tải hoạt động trong vùng biển thí điểm.
VELOCITY_PRIOR_MS = 10.0


@dataclass
class KalmanEstimate:
    """Kết quả nội suy tại một thời điểm."""

    lat: float
    lon: float
    speed_kn: float
    course_deg: float
    # Bán kính bất định một xích-ma của vị trí, tính bằng mét
    position_sigma_m: float
    # Khoảng cách thời gian tới bản ghi AIS gần nhất, tính bằng giây
    gap_to_nearest_s: float
    n_observations: int


class ConstantVelocityKalman:
    """Bộ làm trơn Kalman với mô hình vận tốc không đổi.

    Tham số ``process_noise`` là độ lệch chuẩn của gia tốc nhiễu trắng, đơn vị
    mét trên giây bình phương; nó quyết định mức độ hệ thống cho phép phương tiện
    đổi hướng và đổi tốc giữa hai quan trắc. Tham số ``measurement_noise`` là độ
    lệch chuẩn sai số vị trí của bản ghi AIS, đơn vị mét.
    """

    def __init__(self, process_noise: float = 0.35, measurement_noise: float = 45.0):
        self.q = float(process_noise)
        self.r = float(measurement_noise)

    # -- Ma trận mô hình ---------------------------------------------------
    @staticmethod
    def _transition(dt: float) -> np.ndarray:
        F = np.eye(4)
        F[0, 2] = dt
        F[1, 3] = dt
        return F

    def _process_cov(self, dt: float) -> np.ndarray:
        """Hiệp phương sai nhiễu quá trình cho mô hình gia tốc trắng rời rạc."""
        q = self.q**2
        dt2 = dt * dt
        dt3 = dt2 * dt / 2.0
        dt4 = dt2 * dt2 / 4.0
        Q = np.zeros((4, 4))
        Q[0, 0] = Q[1, 1] = dt4 * q
        Q[2, 2] = Q[3, 3] = dt2 * q
        Q[0, 2] = Q[2, 0] = Q[1, 3] = Q[3, 1] = dt3 * q
        # Thêm một lượng rất nhỏ trên đường chéo để bảo đảm khả nghịch
        return Q + np.eye(4) * 1e-9

    # -- Làm trơn ----------------------------------------------------------
    def smooth_to_time(
        self, records: Sequence[dict], target_time_s: float
    ) -> Optional[KalmanEstimate]:
        """Ước lượng trạng thái của một phương tiện tại ``target_time_s``.

        ``records`` là các bản ghi AIS của cùng một MMSI, mỗi bản ghi có các khoá
        ``timestamp``, ``lat``, ``lon``. Danh sách không cần sắp xếp trước.

        Thuật toán gồm ba giai đoạn: dựng trục thời gian chứa cả các mốc quan
        trắc lẫn thời điểm mục tiêu; chạy lọc Kalman tiến trên trục đó; chạy
        truy hồi Rauch–Tung–Striebel ngược để thu được ước lượng làm trơn.
        """
        if not records:
            return None

        recs = sorted(records, key=lambda r: float(r["timestamp"]))

        # Hệ quy chiếu phẳng cục bộ, lấy gốc tại quan trắc đầu tiên
        lat_ref = float(recs[0]["lat"])
        lon_ref = float(recs[0]["lon"])
        m_lat, m_lon = meters_per_degree(lat_ref)

        def to_local(lat: float, lon: float) -> Tuple[float, float]:
            return ((lon - lon_ref) * m_lon, (lat - lat_ref) * m_lat)

        # ---- Giai đoạn 1: dựng trục thời gian ---------------------------
        obs_times = [float(r["timestamp"]) for r in recs]
        timeline = sorted(set(obs_times + [float(target_time_s)]))
        index_of = {t: i for i, t in enumerate(timeline)}
        target_idx = index_of[float(target_time_s)]

        # Nhóm quan trắc theo mốc thời gian, phòng trường hợp trùng nhãn thời gian
        obs_at: Dict[int, List[np.ndarray]] = {}
        for r in recs:
            i = index_of[float(r["timestamp"])]
            e, n = to_local(float(r["lat"]), float(r["lon"]))
            obs_at.setdefault(i, []).append(np.array([e, n], dtype=float))

        N = len(timeline)
        H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
        R = np.eye(2) * (self.r**2)

        # ---- Giai đoạn 2: lọc tiến ---------------------------------------
        x_pred = [np.zeros(4) for _ in range(N)]
        P_pred = [np.eye(4) for _ in range(N)]
        x_filt = [np.zeros(4) for _ in range(N)]
        P_filt = [np.eye(4) for _ in range(N)]
        F_list = [np.eye(4) for _ in range(N)]

        # Khởi tạo tại mốc đầu tiên của trục thời gian
        first_obs = obs_at.get(0)
        if first_obs is not None:
            x0 = np.array([first_obs[0][0], first_obs[0][1], 0.0, 0.0])
            P0 = np.diag([self.r**2, self.r**2,
                          VELOCITY_PRIOR_MS**2, VELOCITY_PRIOR_MS**2])
        else:
            # Mốc đầu là thời điểm mục tiêu, nằm trước mọi quan trắc.
            # Khởi tạo lỏng; lượt truy hồi ngược sẽ hiệu chỉnh lại.
            e0, n0 = to_local(float(recs[0]["lat"]), float(recs[0]["lon"]))
            x0 = np.array([e0, n0, 0.0, 0.0])
            P0 = np.diag([(5.0 * self.r) ** 2, (5.0 * self.r) ** 2,
                          VELOCITY_PRIOR_MS**2, VELOCITY_PRIOR_MS**2])

        x_pred[0], P_pred[0] = x0.copy(), P0.copy()
        x, P = x0.copy(), P0.copy()
        if first_obs is not None:
            for z in first_obs:
                y = z - H @ x
                S = H @ P @ H.T + R
                K = P @ H.T @ np.linalg.inv(S)
                x = x + K @ y
                P = (np.eye(4) - K @ H) @ P
        x_filt[0], P_filt[0] = x.copy(), P.copy()

        for k in range(1, N):
            dt = timeline[k] - timeline[k - 1]
            F = self._transition(dt)
            F_list[k] = F
            x = F @ x_filt[k - 1]
            P = F @ P_filt[k - 1] @ F.T + self._process_cov(dt)
            x_pred[k], P_pred[k] = x.copy(), P.copy()

            for z in obs_at.get(k, []):
                y = z - H @ x
                S = H @ P @ H.T + R
                K = P @ H.T @ np.linalg.inv(S)
                x = x + K @ y
                P = (np.eye(4) - K @ H) @ P
            x_filt[k], P_filt[k] = x.copy(), P.copy()

        # ---- Giai đoạn 3: truy hồi Rauch–Tung–Striebel --------------------
        x_smooth = [xf.copy() for xf in x_filt]
        P_smooth = [Pf.copy() for Pf in P_filt]

        for k in range(N - 2, -1, -1):
            try:
                P_pred_inv = np.linalg.inv(P_pred[k + 1])
            except np.linalg.LinAlgError:  # pragma: no cover
                P_pred_inv = np.linalg.pinv(P_pred[k + 1])
            C = P_filt[k] @ F_list[k + 1].T @ P_pred_inv
            x_smooth[k] = x_filt[k] + C @ (x_smooth[k + 1] - x_pred[k + 1])
            P_smooth[k] = P_filt[k] + C @ (P_smooth[k + 1] - P_pred[k + 1]) @ C.T

        xs = x_smooth[target_idx]
        Ps = P_smooth[target_idx]

        lat = lat_ref + xs[1] / m_lat
        lon = lon_ref + xs[0] / m_lon
        speed_ms = float(np.hypot(xs[2], xs[3]))
        course = float(np.degrees(np.arctan2(xs[2], xs[3])) % 360.0)
        sigma = float(np.sqrt(max((Ps[0, 0] + Ps[1, 1]) / 2.0, 0.0)))
        gap = float(min(abs(t - float(target_time_s)) for t in obs_times))

        return KalmanEstimate(
            lat=float(lat), lon=float(lon),
            speed_kn=speed_ms / 0.514444,
            course_deg=course,
            position_sigma_m=sigma,
            gap_to_nearest_s=gap,
            n_observations=len(recs),
        )


def linear_interpolate_to_time(
    records: Sequence[dict], target_time_s: float
) -> Optional[KalmanEstimate]:
    """Nội suy tuyến tính — phương án cơ sở để so sánh với bộ làm trơn Kalman.

    Phép nội suy này chỉ dùng hai bản ghi lân cận thời điểm mục tiêu, nên toàn bộ
    nhiễu đo của hai điểm mút truyền thẳng vào kết quả mà không được trung bình
    hoá qua chuỗi quan trắc.
    """
    if not records:
        return None

    recs = sorted(records, key=lambda r: float(r["timestamp"]))
    times = np.array([float(r["timestamp"]) for r in recs], dtype=float)
    lats = np.array([float(r["lat"]) for r in recs], dtype=float)
    lons = np.array([float(r["lon"]) for r in recs], dtype=float)

    lat = float(np.interp(target_time_s, times, lats))
    lon = float(np.interp(target_time_s, times, lons))
    gap = float(np.min(np.abs(times - target_time_s)))

    if len(recs) >= 2:
        i = int(np.clip(np.searchsorted(times, target_time_s), 1, len(recs) - 1))
        dt = max(times[i] - times[i - 1], 1e-3)
        m_lat, m_lon = meters_per_degree(lats[i])
        de = (lons[i] - lons[i - 1]) * m_lon
        dn = (lats[i] - lats[i - 1]) * m_lat
        speed = float(np.hypot(de, dn) / dt / 0.514444)
        course = float(np.degrees(np.arctan2(de, dn)) % 360.0)
    else:
        speed, course = 0.0, 0.0

    return KalmanEstimate(
        lat=lat, lon=lon, speed_kn=speed, course_deg=course,
        position_sigma_m=float("nan"), gap_to_nearest_s=gap,
        n_observations=len(recs),
    )
