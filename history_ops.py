"""GPS position history statistics and optimization helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import delete, func

from app.database import get_now_to_utc, session_scope
from plugins.GpsTracker.models.GpsDevice import GpsDevice
from plugins.GpsTracker.models.GpsPosition import GpsPosition
from plugins.GpsTracker.utils import calculate_distance

DEFAULT_DEDUPE_DISTANCE_M = 15.0
DEFAULT_THIN_DISTANCE_M = 30.0
DEFAULT_THIN_INTERVAL_MIN = 15
SUGGEST_OLDER_DAYS = 90
SUGGEST_MIN_DELETE = 20

_MODES = ("older_than", "deduplicate", "thin_stationary", "clear_device")


def _dt_str(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _as_float(value, default: float) -> float:
    if value in (None, ""):
        return float(default)
    return float(value)


def _as_int(value, default: int) -> int:
    if value in (None, ""):
        return int(default)
    return int(value)


def _as_bool(value, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _optional_device_id(value) -> Optional[int]:
    if value in (None, ""):
        return None
    return int(value)


class _Point:
    __slots__ = ("id", "added", "lat", "lon")

    def __init__(self, row_id: int, added: datetime, lat: float, lon: float):
        self.id = int(row_id)
        self.added = added
        self.lat = float(lat)
        self.lon = float(lon)


def _load_points(session, device_id: Optional[int] = None) -> Dict[int, List[_Point]]:
    q = session.query(
        GpsPosition.id,
        GpsPosition.device_id,
        GpsPosition.added,
        GpsPosition.lat,
        GpsPosition.lon,
    )
    if device_id is not None:
        q = q.filter(GpsPosition.device_id == int(device_id))
    q = q.order_by(GpsPosition.device_id, GpsPosition.added, GpsPosition.id)
    by_device: Dict[int, List[_Point]] = {}
    for row_id, dev_id, added, lat, lon in q.yield_per(2000):
        if lat is None or lon is None or added is None:
            continue
        by_device.setdefault(int(dev_id), []).append(_Point(row_id, added, lat, lon))
    return by_device


def _iter_proximity_segments(points: Sequence[_Point], distance_m: float) -> Iterable[List[_Point]]:
    if not points:
        return
    segment: List[_Point] = [points[0]]
    anchor = points[0]
    for point in points[1:]:
        dist = calculate_distance(anchor.lat, anchor.lon, point.lat, point.lon)
        if dist < distance_m:
            segment.append(point)
            continue
        yield segment
        segment = [point]
        anchor = point
    yield segment


def _ids_to_delete_in_segment(
    segment: Sequence[_Point],
    *,
    interval_minutes: Optional[int] = None,
) -> List[int]:
    """Keep first + last (and optional time anchors); return middle IDs to delete."""
    if len(segment) <= 2:
        return []

    keep_indexes = {0, len(segment) - 1}
    if interval_minutes is not None and interval_minutes > 0:
        last_kept_time = segment[0].added
        for index in range(1, len(segment) - 1):
            point = segment[index]
            delta_min = (point.added - last_kept_time).total_seconds() / 60.0
            if delta_min >= interval_minutes:
                keep_indexes.add(index)
                last_kept_time = point.added

    return [segment[i].id for i in range(len(segment)) if i not in keep_indexes]


def _collect_delete_ids(
    by_device: Dict[int, List[_Point]],
    *,
    distance_m: float,
    interval_minutes: Optional[int] = None,
) -> List[int]:
    delete_ids: List[int] = []
    for points in by_device.values():
        for segment in _iter_proximity_segments(points, distance_m):
            delete_ids.extend(
                _ids_to_delete_in_segment(segment, interval_minutes=interval_minutes)
            )
    return delete_ids


def _count_older_than(session, days: int, device_id: Optional[int] = None) -> int:
    cutoff = get_now_to_utc() - timedelta(days=int(days))
    q = session.query(func.count(GpsPosition.id)).filter(GpsPosition.added < cutoff)
    if device_id is not None:
        q = q.filter(GpsPosition.device_id == int(device_id))
    return int(q.scalar() or 0)


def _device_titles(session) -> Dict[int, str]:
    rows = session.query(GpsDevice.id, GpsDevice.title).all()
    return {int(row_id): (title or str(row_id)) for row_id, title in rows}


def get_history_stats(device_id: Optional[int] = None) -> dict:
    device_filter = _optional_device_id(device_id)
    with session_scope() as session:
        base = session.query(GpsPosition)
        if device_filter is not None:
            base = base.filter(GpsPosition.device_id == device_filter)

        total = int(base.with_entities(func.count(GpsPosition.id)).scalar() or 0)
        oldest = base.with_entities(func.min(GpsPosition.added)).scalar()
        newest = base.with_entities(func.max(GpsPosition.added)).scalar()

        grouped = (
            session.query(
                GpsPosition.device_id,
                func.count(GpsPosition.id),
                func.min(GpsPosition.added),
                func.max(GpsPosition.added),
            )
        )
        if device_filter is not None:
            grouped = grouped.filter(GpsPosition.device_id == device_filter)
        grouped = grouped.group_by(GpsPosition.device_id).order_by(GpsPosition.device_id).all()

        titles = _device_titles(session)
        by_device = [
            {
                "device_id": int(dev_id),
                "title": titles.get(int(dev_id), str(dev_id)),
                "count": int(count),
                "oldest": _dt_str(dev_oldest),
                "newest": _dt_str(dev_newest),
            }
            for dev_id, count, dev_oldest, dev_newest in grouped
        ]

        points_by_device = _load_points(session, device_filter)
        approx_duplicates = len(
            _collect_delete_ids(
                points_by_device,
                distance_m=DEFAULT_DEDUPE_DISTANCE_M,
                interval_minutes=None,
            )
        )
        approx_stationary_redundant = len(
            _collect_delete_ids(
                points_by_device,
                distance_m=DEFAULT_THIN_DISTANCE_M,
                interval_minutes=DEFAULT_THIN_INTERVAL_MIN,
            )
        )
        older_90 = _count_older_than(session, SUGGEST_OLDER_DAYS, device_filter)

    suggestions: List[dict] = []
    if older_90 >= SUGGEST_MIN_DELETE:
        suggestions.append(
            {
                "mode": "older_than",
                "params": {"days": SUGGEST_OLDER_DAYS, "device_id": device_filter},
                "estimated_delete": older_90,
                "reason": (
                    f"{older_90} positions older than {SUGGEST_OLDER_DAYS} days; "
                    "safe retention cleanup"
                ),
            }
        )
    if approx_duplicates >= SUGGEST_MIN_DELETE:
        suggestions.append(
            {
                "mode": "deduplicate",
                "params": {
                    "distance_m": DEFAULT_DEDUPE_DISTANCE_M,
                    "device_id": device_filter,
                },
                "estimated_delete": approx_duplicates,
                "reason": (
                    f"About {approx_duplicates} middle points in near-duplicate stays "
                    f"(keep first + last within {DEFAULT_DEDUPE_DISTANCE_M:g} m)"
                ),
            }
        )
    if approx_stationary_redundant >= SUGGEST_MIN_DELETE:
        suggestions.append(
            {
                "mode": "thin_stationary",
                "params": {
                    "distance_m": DEFAULT_THIN_DISTANCE_M,
                    "interval_minutes": DEFAULT_THIN_INTERVAL_MIN,
                    "device_id": device_filter,
                },
                "estimated_delete": approx_stationary_redundant,
                "reason": (
                    f"About {approx_stationary_redundant} redundant stationary pings "
                    f"(keep first + last and anchors every {DEFAULT_THIN_INTERVAL_MIN} min)"
                ),
            }
        )

    return {
        "total": total,
        "oldest": _dt_str(oldest),
        "newest": _dt_str(newest),
        "by_device": by_device,
        "approx_duplicates": approx_duplicates,
        "approx_stationary_redundant": approx_stationary_redundant,
        "suggestions": suggestions,
        "device_id": device_filter,
    }


def _delete_by_ids(session, ids: Sequence[int]) -> int:
    if not ids:
        return 0
    deleted = 0
    chunk_size = 1000
    id_list = list(ids)
    for offset in range(0, len(id_list), chunk_size):
        chunk = id_list[offset : offset + chunk_size]
        result = session.execute(delete(GpsPosition).where(GpsPosition.id.in_(chunk)))
        deleted += int(result.rowcount or 0)
    return deleted


def optimize_history(
    mode: str,
    *,
    dry_run: bool = False,
    days: Optional[int] = None,
    distance_m: Optional[float] = None,
    interval_minutes: Optional[int] = None,
    device_id: Optional[int] = None,
) -> dict:
    mode = str(mode or "").strip()
    if mode not in _MODES:
        raise ValueError(f"Unsupported mode: {mode}. Expected one of: {', '.join(_MODES)}")

    dry = _as_bool(dry_run, False)
    device_filter = _optional_device_id(device_id)
    params: Dict[str, Any] = {"device_id": device_filter}

    if mode == "clear_device":
        if device_filter is None:
            raise ValueError("device_id is required for clear_device")
        with session_scope() as session:
            count = int(
                session.query(func.count(GpsPosition.id))
                .filter(GpsPosition.device_id == device_filter)
                .scalar()
                or 0
            )
            if not dry and count:
                session.execute(delete(GpsPosition).where(GpsPosition.device_id == device_filter))
        key = "would_delete" if dry else "deleted"
        return {"ok": True, "mode": mode, "dry_run": dry, key: count, "params": params}

    if mode == "older_than":
        days_value = _as_int(days, SUGGEST_OLDER_DAYS)
        if days_value < 1:
            raise ValueError("days must be >= 1")
        params["days"] = days_value
        cutoff = get_now_to_utc() - timedelta(days=days_value)
        with session_scope() as session:
            q = session.query(func.count(GpsPosition.id)).filter(GpsPosition.added < cutoff)
            if device_filter is not None:
                q = q.filter(GpsPosition.device_id == device_filter)
            count = int(q.scalar() or 0)
            if not dry and count:
                stmt = delete(GpsPosition).where(GpsPosition.added < cutoff)
                if device_filter is not None:
                    stmt = stmt.where(GpsPosition.device_id == device_filter)
                session.execute(stmt)
        key = "would_delete" if dry else "deleted"
        return {"ok": True, "mode": mode, "dry_run": dry, key: count, "params": params}

    if mode == "deduplicate":
        dist = _as_float(distance_m, DEFAULT_DEDUPE_DISTANCE_M)
        if dist <= 0:
            raise ValueError("distance_m must be > 0")
        params["distance_m"] = dist
        with session_scope() as session:
            points = _load_points(session, device_filter)
            delete_ids = _collect_delete_ids(points, distance_m=dist, interval_minutes=None)
            count = len(delete_ids)
            if not dry and delete_ids:
                count = _delete_by_ids(session, delete_ids)
        key = "would_delete" if dry else "deleted"
        return {"ok": True, "mode": mode, "dry_run": dry, key: count, "params": params}

    # thin_stationary
    dist = _as_float(distance_m, DEFAULT_THIN_DISTANCE_M)
    interval = _as_int(interval_minutes, DEFAULT_THIN_INTERVAL_MIN)
    if dist <= 0:
        raise ValueError("distance_m must be > 0")
    if interval < 1:
        raise ValueError("interval_minutes must be >= 1")
    params["distance_m"] = dist
    params["interval_minutes"] = interval
    with session_scope() as session:
        points = _load_points(session, device_filter)
        delete_ids = _collect_delete_ids(
            points,
            distance_m=dist,
            interval_minutes=interval,
        )
        count = len(delete_ids)
        if not dry and delete_ids:
            count = _delete_by_ids(session, delete_ids)
    key = "would_delete" if dry else "deleted"
    return {"ok": True, "mode": mode, "dry_run": dry, key: count, "params": params}
