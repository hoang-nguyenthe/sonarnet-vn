"""Observation labels, deliberately independent from legal/identity claims."""
MISSING_DATA = 'MISSING_DATA'
STATE_LABELS = {
    'AIS_OK': 'Ghép được; chờ xác minh',
    'AIS_MISMATCH': 'Đang xác minh: kích thước lệch',
    'DARK': 'Không ghép được',
    MISSING_DATA: 'Thiếu dữ liệu',
}
EVALUATION_STATES = tuple(STATE_LABELS)


def pending_review():
    return {'status': 'pending', 'reviewer': None, 'conclusion': None}
