"""Shared, versioned review decisions for published SAR observations."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3

from review_workspace import OPERATIONAL_DECISIONS, tile_identity

DECISION_COLORS = dict(zip(OPERATIONAL_DECISIONS, ('#d17a1c', '#3979b4', '#23856c')))
PENDING = 'Chưa có quyết định'


class DecisionConflict(ValueError):
    """The last decision changed while someone was reviewing this point."""


def database_path(root):
    return Path(os.environ.get('SONARNET_REVIEW_DB', root / '.sonarnet' / 'decisions.sqlite3'))


def open_database(path):
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def has_decision_table(connection):
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE name='manager_decisions' AND type='table'"
    ).fetchone() is not None


def read_snapshot(path):
    """Read one consistent snapshot, including its revision, for all viewers."""
    if not path.is_file():
        return 0, {}
    with closing(open_database(path)) as connection:
        if not has_decision_table(connection):
            return 0, {}
        rows = connection.execute('''
            SELECT d.* FROM manager_decisions AS d JOIN (
                SELECT MAX(revision) AS revision FROM manager_decisions GROUP BY point_id, evidence_id
            ) AS latest USING (revision)
        ''').fetchall()
    revision = max((row['revision'] for row in rows), default=0)
    decisions = {(row['point_id'], row['evidence_id']): dict(row) for row in rows}
    return revision, decisions


def latest_revision(path):
    if not path.is_file():
        return 0
    with closing(open_database(path)) as connection:
        if not has_decision_table(connection):
            return 0
        return connection.execute('SELECT COALESCE(MAX(revision), 0) FROM manager_decisions').fetchone()[0]


def point_decisions(result, decisions):
    if not result or not decisions:
        return {}
    relevant = {point_id for point_id, _ in decisions}
    tile_keys = {p['tile_key'] for p in result['detections'] if p['id'] in relevant}
    identities = {tile['key']: tile_identity(tile) for tile in result['tiles'] if tile['key'] in tile_keys}
    return {p['id']: decisions[p['id'], identities[p['tile_key']]]
            for p in result['detections']
            if p['id'] in relevant and (p['id'], identities[p['tile_key']]) in decisions}


def save_decision(path, tile, point_id, outcome, basis, expected_revision):
    """Append atomically and refuse to replace a decision from a stale form."""
    prefix = f"{tile['key']}/"
    if not point_id.startswith(prefix) or not any(
        str(p['id']) == point_id.removeprefix(prefix) for p in tile['detections']
    ):
        raise ValueError('Điểm đã chọn không còn khớp ảnh nguồn.')
    basis = basis.strip()
    if outcome not in OPERATIONAL_DECISIONS or not basis or len(basis) > 1200:
        raise ValueError('Chọn hướng xử lý và nhập căn cứ từ 1 đến 1.200 ký tự.')
    identity = tile_identity(tile)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with closing(open_database(path)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS manager_decisions (
                revision INTEGER PRIMARY KEY, point_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
                outcome TEXT NOT NULL, basis TEXT NOT NULL, decided_at TEXT NOT NULL
            )
        ''')
        connection.execute('''
            CREATE INDEX IF NOT EXISTS decisions_by_point
            ON manager_decisions (point_id, evidence_id, revision)
        ''')
        actual = connection.execute('''
            SELECT COALESCE(MAX(revision), 0) FROM manager_decisions
            WHERE point_id=? AND evidence_id=?
        ''', (point_id, identity)).fetchone()[0]
        if actual != expected_revision:
            raise DecisionConflict('Điểm này vừa được cập nhật. Xem lại quyết định mới trước khi lưu.')
        timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        return connection.execute('''
            INSERT INTO manager_decisions (point_id, evidence_id, outcome, basis, decided_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (point_id, identity, outcome, basis, timestamp)).lastrowid


def decision_history(path, point_id, evidence_id):
    if not path.is_file():
        return []
    with closing(open_database(path)) as connection:
        if not has_decision_table(connection):
            return []
        return [dict(row) for row in connection.execute('''
            SELECT * FROM manager_decisions
            WHERE point_id=? AND evidence_id=? ORDER BY revision DESC
        ''', (point_id, evidence_id))]
