"""MCP integration helpers for GpsTracker plugin."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import delete, desc, or_

from app.core.lib.mcp_contract import (
    build_plugin_mcp_descriptors,
    revision_from_datetime,
    revision_from_dict,
    validate_entity_payload,
)
from app.core.lib.plugin_binding import sync_object_link, validate_object_exists
from app.database import row2dict, session_scope

from plugins.GpsTracker.geocoding_providers import is_provider_disabled, resolve_address
from plugins.GpsTracker import history_ops
from plugins.GpsTracker.models.GpsDevice import GpsDevice
from plugins.GpsTracker.models.GpsLocation import GpsLocation
from plugins.GpsTracker.models.GpsPosition import GpsPosition

PLUGIN_NAME = "GpsTracker"
DEVICES = "devices"
LOCATIONS = "locations"
POSITIONS = "positions"

_DEVICE_WRITABLE_FIELDS = ("title", "device_id", "linked_object")
_LOCATION_WRITABLE_FIELDS = ("title", "lat", "lon", "range", "is_home")
_DEVICE_READONLY_FIELDS = ("id", "lat", "lon", "updated")
_LOCATION_READONLY_FIELDS = ("id",)

_PLUGIN_NOTES = [
    "Devices store external tracker id in device_id; lat/lon/updated are updated on each position (read-only via MCP).",
    "Bind a device to osysHome with linked_object (binding_mode: object). Object must have properties: "
    "latlon, location, home, address, home_distance, battery, isCharging.",
    "Locations are geofences; exactly one should have is_home=true for home/home_distance calculation.",
    "Positions are append-only history; use add_position or delete_position, not upsert_entity.",
    "add_position runs the same pipeline as REST/OwnTracks/uLogger: geofence match, reverse geocoding, linked_object updates.",
    "address_provider in config controls reverse geocoding (disabled, openstreetmap, google, yandex, ...).",
    "Pass address in add_position to skip reverse geocoding for that point.",
    "max_accuracy_m in config: discard positions when reported accuracy (meters) exceeds this value; 0 = disabled.",
    "max_speed_kmh in config: discard positions when implied speed from the previous point exceeds this value; 0 = disabled.",
    "Use resolve_address to preview geocoding at lat/lon with current plugin config.",
    "list_entities on positions defaults to newest-first (order_desc=true).",
    "Use get_history_stats for totals/per-device counts and optimization suggestions.",
    "Use optimize_history to clean history: older_than, deduplicate, thin_stationary, clear_device "
    "(always dry_run=true first). deduplicate/thin keep first+last of each stay segment.",
]

_ENTITY_AUTHORING_PROMPT = "osys_gpstracker_entity_authoring"


def _plugin_instance():
    try:
        from app.core.main.PluginsHelper import plugins
        return plugins.get(PLUGIN_NAME, {}).get("instance")
    except Exception:
        return None


def mcp_capabilities() -> dict:
    return {
        "mcp_version": 1,
        "entities": True,
        "config_schema": True,
        "notes": list(_PLUGIN_NOTES),
        "collections": [
            {
                "id": DEVICES,
                "title": "GPS Devices",
                "binding_mode": "object",
                "writable": True,
                "has_code": False,
                "list_filters": ["query", "linked_object", "has_linked_object"],
                "default_sort": "title asc, id asc",
                "writable_fields": list(_DEVICE_WRITABLE_FIELDS),
                "description": (
                    "GPS tracker devices. device_id is the external identifier from uLogger/OwnTracks/REST. "
                    "linked_object binds to an osysHome object for property updates."
                ),
            },
            {
                "id": LOCATIONS,
                "title": "GPS Locations",
                "binding_mode": "none",
                "writable": True,
                "has_code": False,
                "list_filters": ["query", "is_home"],
                "default_sort": "title asc, id asc",
                "writable_fields": list(_LOCATION_WRITABLE_FIELDS),
                "description": (
                    "Geofence zones (lat/lon center + range in meters). "
                    "One location with is_home=true defines the home zone."
                ),
            },
            {
                "id": POSITIONS,
                "title": "GPS Positions",
                "binding_mode": "none",
                "writable": False,
                "has_code": False,
                "list_filters": ["device_id", "query", "start_time", "end_time", "order_desc"],
                "default_sort": "added desc, id desc",
                "description": "Position history (read-only). Use add_position to append; delete_position to remove.",
            },
        ],
        "operations": [
            "add_position",
            "get_latest_position",
            "delete_position",
            "resolve_address",
            "get_history_stats",
            "optimize_history",
        ],
        "operation_schemas": {
            "add_position": {
                "description": "Append GPS position and run geofence/geocoding/linked_object pipeline",
                "params": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string", "description": "External device identifier (device_id)"},
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "alt": {"type": "number"},
                        "accuracy": {"type": "number"},
                        "speed": {"type": "number"},
                        "battery": {"type": "number"},
                        "charging": {"type": "boolean"},
                        "provider": {"type": "string"},
                        "address": {"type": "string", "description": "Skip reverse geocoding when set"},
                        "added": {"type": "string", "description": "ISO 8601 or YYYY-MM-DD HH:MM:SS"},
                    },
                    "required": ["device", "lat", "lon"],
                },
            },
            "get_latest_position": {
                "description": "Latest stored position for a device (by internal id or external device_id)",
                "params": {
                    "type": "object",
                    "properties": {
                        "device_id": {"type": "integer", "description": "Internal device primary key"},
                        "device": {"type": "string", "description": "External device identifier"},
                    },
                },
            },
            "delete_position": {
                "description": "Delete a single position record by id",
                "params": {
                    "type": "object",
                    "properties": {
                        "position_id": {"type": "integer", "description": "Position row id"},
                    },
                    "required": ["position_id"],
                },
            },
            "resolve_address": {
                "description": "Reverse-geocode lat/lon using plugin address_provider config",
                "params": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                    },
                    "required": ["lat", "lon"],
                },
            },
            "get_history_stats": {
                "description": (
                    "History totals, per-device counts, approximate redundant counts, "
                    "and optimization suggestions"
                ),
                "params": {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "integer",
                            "description": "Optional internal device primary key filter",
                        },
                    },
                },
            },
            "optimize_history": {
                "description": (
                    "Optimize position history. Modes: older_than, deduplicate, thin_stationary, "
                    "clear_device. For stay compression, keep first + last of each proximity segment "
                    "(last = last presence time). Prefer dry_run=true first."
                ),
                "params": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": [
                                "older_than",
                                "deduplicate",
                                "thin_stationary",
                                "clear_device",
                            ],
                        },
                        "dry_run": {
                            "type": "boolean",
                            "default": False,
                            "description": "Preview deletions without writing",
                        },
                        "days": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Retention days for older_than",
                        },
                        "distance_m": {
                            "type": "number",
                            "description": "Proximity radius for deduplicate/thin_stationary",
                        },
                        "interval_minutes": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Anchor interval for thin_stationary",
                        },
                        "device_id": {
                            "type": "integer",
                            "description": "Internal device PK (required for clear_device)",
                        },
                    },
                    "required": ["mode"],
                },
            },
        },
    }


def mcp_config_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "address_provider": {
                "type": "string",
                "enum": [
                    "disabled",
                    "openstreetmap",
                    "bigdatacloud",
                    "mapsco",
                    "google",
                    "yandex",
                    "locationiq",
                ],
                "default": "disabled",
                "description": "Reverse geocoding provider for position address when not in a geofence",
            },
            "google_api_key": {"type": "string", "writeOnly": True},
            "yandex_api_key": {"type": "string", "writeOnly": True},
            "locationiq_api_key": {"type": "string", "writeOnly": True},
            "mapsco_api_key": {"type": "string", "writeOnly": True},
            "max_accuracy_m": {
                "type": "number",
                "minimum": 0,
                "default": 0,
                "description": "Discard positions when reported accuracy (meters) exceeds this value; 0 disables filtering",
            },
            "max_speed_kmh": {
                "type": "number",
                "minimum": 0,
                "default": 0,
                "description": "Discard positions when implied speed from the previous point (km/h) exceeds this value; 0 disables filtering",
            },
        },
    }


def _collection_meta(collection: str) -> dict:
    for item in mcp_capabilities()["collections"]:
        if item["id"] == collection:
            return item
    raise ValueError(f"Unsupported collection: {collection}")


def _device_to_dict(row: GpsDevice) -> dict:
    data = row2dict(row)
    if row.updated:
        data["updated"] = row.updated.isoformat(sep=" ", timespec="seconds")
    return data


def _location_to_dict(row: GpsLocation) -> dict:
    return row2dict(row)


def _position_to_dict(row: GpsPosition) -> dict:
    data = row2dict(row)
    if row.added:
        data["added"] = row.added.isoformat(sep=" ", timespec="seconds")
    return data


def _parse_datetime(value) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def _parse_optional_bool(value) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _query_filter(model, query: str):
    like = f"%{query}%"
    if model is GpsDevice:
        return or_(model.title.ilike(like), model.device_id.ilike(like), model.linked_object.ilike(like))
    if model is GpsLocation:
        return or_(model.title.ilike(like))
    if model is GpsPosition:
        return or_(model.address.ilike(like), model.provider.ilike(like))
    return None


def _merge_device_payload(payload: dict, entity_id=None) -> dict:
    merged = dict(payload or {})
    if entity_id in (None, ""):
        return merged
    try:
        current = mcp_get_entity(DEVICES, entity_id)
    except ValueError:
        return merged
    for field in _DEVICE_WRITABLE_FIELDS:
        if field not in merged and field in current:
            merged[field] = current[field]
    return merged


def _merge_location_payload(payload: dict, entity_id=None) -> dict:
    merged = dict(payload or {})
    if entity_id in (None, ""):
        return merged
    try:
        current = mcp_get_entity(LOCATIONS, entity_id)
    except ValueError:
        return merged
    for field in _LOCATION_WRITABLE_FIELDS:
        if field not in merged and field in current:
            merged[field] = current[field]
    return merged


def _find_device_by_key(session, device_key: str, exclude_id=None):
    key = str(device_key or "").strip()
    if not key:
        return None
    query = session.query(GpsDevice).filter(GpsDevice.device_id == key)
    if exclude_id not in (None, ""):
        query = query.filter(GpsDevice.id != int(exclude_id))
    return query.one_or_none()


def _find_location_by_title(session, title: str, exclude_id=None):
    name = str(title or "").strip()
    if not name:
        return None
    query = session.query(GpsLocation).filter(GpsLocation.title == name)
    if exclude_id not in (None, ""):
        query = query.filter(GpsLocation.id != int(exclude_id))
    return query.order_by(GpsLocation.id).first()


def mcp_entity_schema(collection: str) -> dict:
    _collection_meta(collection)
    if collection == DEVICES:
        return {
            "type": "object",
            "description": "GPS device bound to an external tracker id and optional osysHome object.",
            "properties": {
                "id": {"type": "integer", "readOnly": True},
                "title": {"type": "string", "description": "Display name in admin UI"},
                "device_id": {
                    "type": "string",
                    "description": "External device identifier (uLogger user_tid, OwnTracks tid, REST device)",
                },
                "linked_object": {"type": "string", "description": "Bound osysHome object name"},
                "lat": {"type": "number", "readOnly": True, "description": "Last known latitude"},
                "lon": {"type": "number", "readOnly": True, "description": "Last known longitude"},
                "updated": {"type": "string", "readOnly": True, "description": "Last position timestamp"},
            },
            "required": ["title"],
        }
    if collection == LOCATIONS:
        return {
            "type": "object",
            "description": "Geofence zone with center coordinates and radius in meters.",
            "properties": {
                "id": {"type": "integer", "readOnly": True},
                "title": {"type": "string", "description": "Zone name (written to linked_object.location)"},
                "lat": {"type": "number", "description": "Center latitude"},
                "lon": {"type": "number", "description": "Center longitude"},
                "range": {"type": "number", "description": "Radius in meters (distance < range means inside)"},
                "is_home": {"type": "boolean", "description": "Mark as home zone for home/home_distance"},
            },
            "required": ["title", "lat", "lon", "range"],
        }
    if collection == POSITIONS:
        return {
            "type": "object",
            "readOnly": True,
            "description": "Historical GPS point (append via add_position only).",
            "properties": {
                "id": {"type": "integer", "readOnly": True},
                "added": {"type": "string", "readOnly": True},
                "device_id": {"type": "integer", "readOnly": True, "description": "Internal GpsDevice.id"},
                "lat": {"type": "number", "readOnly": True},
                "lon": {"type": "number", "readOnly": True},
                "alt": {"type": "number", "readOnly": True},
                "accuracy": {"type": "number", "readOnly": True},
                "speed": {"type": "number", "readOnly": True},
                "battery": {"type": "number", "readOnly": True},
                "charging": {"type": "boolean", "readOnly": True},
                "provider": {"type": "string", "readOnly": True},
                "address": {"type": "string", "readOnly": True},
            },
        }
    raise ValueError(f"Unsupported collection: {collection}")


def mcp_list_entities(
    collection: str,
    query: str = None,
    limit: int = 100,
    device_id: Optional[int] = None,
    order_desc: Optional[bool] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    linked_object: Optional[str] = None,
    has_linked_object: Optional[bool] = None,
    is_home: Optional[bool] = None,
) -> List[dict]:
    limit = max(1, min(int(limit or 100), 5000))
    if collection == DEVICES:
        with session_scope() as session:
            q = session.query(GpsDevice)
            if query:
                q = q.filter(_query_filter(GpsDevice, query))
            linked_obj = str(linked_object or "").strip()
            if linked_obj:
                q = q.filter(GpsDevice.linked_object == linked_obj)
            binding_filter = _parse_optional_bool(has_linked_object)
            if binding_filter is True:
                q = q.filter(GpsDevice.linked_object.isnot(None), GpsDevice.linked_object != "")
            elif binding_filter is False:
                q = q.filter(or_(GpsDevice.linked_object.is_(None), GpsDevice.linked_object == ""))
            rows = q.order_by(GpsDevice.title, GpsDevice.id).limit(limit).all()
            return [_device_to_dict(row) for row in rows]
    if collection == LOCATIONS:
        with session_scope() as session:
            q = session.query(GpsLocation)
            if query:
                q = q.filter(_query_filter(GpsLocation, query))
            home_filter = _parse_optional_bool(is_home)
            if home_filter is not None:
                q = q.filter(GpsLocation.is_home == home_filter)
            rows = q.order_by(GpsLocation.title, GpsLocation.id).limit(limit).all()
            return [_location_to_dict(row) for row in rows]
    if collection == POSITIONS:
        with session_scope() as session:
            q = session.query(GpsPosition)
            if device_id not in (None, ""):
                q = q.filter(GpsPosition.device_id == int(device_id))
            start_dt = _parse_datetime(start_time)
            end_dt = _parse_datetime(end_time)
            if start_dt is not None:
                q = q.filter(GpsPosition.added >= start_dt)
            if end_dt is not None:
                q = q.filter(GpsPosition.added <= end_dt)
            if query:
                q = q.filter(_query_filter(GpsPosition, query))
            sort_desc = order_desc if order_desc is not None else True
            if sort_desc:
                q = q.order_by(desc(GpsPosition.added), desc(GpsPosition.id))
            else:
                q = q.order_by(GpsPosition.added, GpsPosition.id)
            rows = q.limit(limit).all()
            return [_position_to_dict(row) for row in rows]
    raise ValueError(f"Unsupported collection: {collection}")


def mcp_get_entity(collection: str, entity_id) -> dict:
    with session_scope() as session:
        if collection == DEVICES:
            row = session.query(GpsDevice).filter(GpsDevice.id == int(entity_id)).one_or_none()
            if row is None:
                raise ValueError(f"Device not found: {entity_id}")
            return _device_to_dict(row)
        if collection == LOCATIONS:
            row = session.query(GpsLocation).filter(GpsLocation.id == int(entity_id)).one_or_none()
            if row is None:
                raise ValueError(f"Location not found: {entity_id}")
            return _location_to_dict(row)
        if collection == POSITIONS:
            row = session.query(GpsPosition).filter(GpsPosition.id == int(entity_id)).one_or_none()
            if row is None:
                raise ValueError(f"Position not found: {entity_id}")
            return _position_to_dict(row)
    raise ValueError(f"Unsupported collection: {collection}")


def _readonly_fields(collection: str) -> tuple:
    if collection == DEVICES:
        return _DEVICE_READONLY_FIELDS
    if collection == LOCATIONS:
        return _LOCATION_READONLY_FIELDS
    return ("id",)


def mcp_upsert_entity(collection: str, payload: dict, entity_id=None) -> dict:
    meta = _collection_meta(collection)
    if not meta.get("writable"):
        raise ValueError(f"Collection '{collection}' is read-only")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    clean_payload = dict(payload)
    for field in _readonly_fields(collection):
        clean_payload.pop(field, None)

    validation = mcp_validate_entity(collection, clean_payload, entity_id=entity_id)
    if not validation.get("ok"):
        raise ValueError(f"validation failed: {validation}")

    if collection == DEVICES:
        merged = _merge_device_payload(clean_payload, entity_id=entity_id)
        with session_scope() as session:
            if entity_id not in (None, ""):
                row = session.query(GpsDevice).filter(GpsDevice.id == int(entity_id)).one_or_none()
                if row is None:
                    raise ValueError(f"Device not found: {entity_id}")
            else:
                device_key = str(merged.get("device_id") or "").strip()
                row = _find_device_by_key(session, device_key) if device_key else None
                if row is None:
                    row = GpsDevice()
                    session.add(row)
            if "title" in merged:
                row.title = merged.get("title")
            if "device_id" in merged:
                row.device_id = str(merged.get("device_id") or "").strip() or None
            if "linked_object" in merged:
                linked_object = str(merged.get("linked_object") or "").strip() or None
                if linked_object:
                    ok, err = sync_object_link(linked_object)
                    if not ok:
                        raise ValueError(err or "object link validation failed")
                row.linked_object = linked_object
            session.commit()
            return _device_to_dict(row)

    if collection == LOCATIONS:
        merged = _merge_location_payload(clean_payload, entity_id=entity_id)
        with session_scope() as session:
            if entity_id not in (None, ""):
                row = session.query(GpsLocation).filter(GpsLocation.id == int(entity_id)).one_or_none()
                if row is None:
                    raise ValueError(f"Location not found: {entity_id}")
            else:
                title = str(merged.get("title") or "").strip()
                row = _find_location_by_title(session, title) if title else None
                if row is None:
                    row = GpsLocation()
                    session.add(row)
            if "title" in merged:
                row.title = merged.get("title")
            if "lat" in merged:
                row.lat = merged.get("lat")
            if "lon" in merged:
                row.lon = merged.get("lon")
            if "range" in merged:
                row.range = merged.get("range")
            if "is_home" in merged:
                if bool(merged.get("is_home")):
                    session.query(GpsLocation).filter(GpsLocation.is_home.is_(True)).update(
                        {GpsLocation.is_home: False},
                        synchronize_session=False,
                    )
                row.is_home = bool(merged.get("is_home"))
            session.commit()
            return _location_to_dict(row)

    raise ValueError(f"Unsupported collection: {collection}")


def mcp_delete_entity(collection: str, entity_id) -> bool:
    meta = _collection_meta(collection)
    if collection == POSITIONS and not meta.get("writable"):
        with session_scope() as session:
            sql = delete(GpsPosition).where(GpsPosition.id == int(entity_id))
            session.execute(sql)
            session.commit()
            return True
    if not meta.get("writable"):
        raise ValueError(f"Collection '{collection}' is read-only")

    with session_scope() as session:
        if collection == DEVICES:
            sql = delete(GpsPosition).where(GpsPosition.device_id == int(entity_id))
            session.execute(sql)
            sql = delete(GpsDevice).where(GpsDevice.id == int(entity_id))
            session.execute(sql)
            session.commit()
            return True
        if collection == LOCATIONS:
            sql = delete(GpsLocation).where(GpsLocation.id == int(entity_id))
            session.execute(sql)
            session.commit()
            return True
        if collection == POSITIONS:
            sql = delete(GpsPosition).where(GpsPosition.id == int(entity_id))
            session.execute(sql)
            session.commit()
            return True
    raise ValueError(f"Unsupported collection: {collection}")


def mcp_validate_entity_code(collection: str, code: str) -> dict:
    raise ValueError(f"Collection '{collection}' does not support code validation")


def mcp_run_entity_dry(collection: str, code: str, context: dict = None) -> dict:
    raise ValueError(f"Collection '{collection}' does not support dry-run code")


def _lookup_latest_position(device_pk=None, device_key: str = None) -> dict:
    if device_pk in (None, "") and not device_key:
        raise ValueError("device_id or device is required")
    with session_scope() as session:
        if device_pk not in (None, ""):
            device_row = session.query(GpsDevice).filter(GpsDevice.id == int(device_pk)).one_or_none()
        else:
            device_row = session.query(GpsDevice).filter(GpsDevice.device_id == device_key).one_or_none()
        if device_row is None:
            raise ValueError("Device not found")
        row = (
            session.query(GpsPosition)
            .filter(GpsPosition.device_id == device_row.id)
            .order_by(desc(GpsPosition.added), desc(GpsPosition.id))
            .first()
        )
        if row is None:
            return {"device": _device_to_dict(device_row), "position": None}
        return {"device": _device_to_dict(device_row), "position": _position_to_dict(row)}


def mcp_invoke(operation: str, params: dict = None) -> dict:
    params = params or {}
    if operation == "add_position":
        device = str(params.get("device") or "").strip()
        lat = params.get("lat")
        lon = params.get("lon")
        if not device or lat is None or lon is None:
            raise ValueError("device, lat, and lon are required")
        instance = _plugin_instance()
        if instance is None:
            raise ValueError("GpsTracker plugin not loaded")
        if instance.addGpsPosition(
            device=device,
            lat=float(lat),
            lon=float(lon),
            alt=params.get("alt"),
            accuracy=params.get("accuracy"),
            speed=params.get("speed"),
            battery=params.get("battery"),
            charging=params.get("charging"),
            provider=params.get("provider"),
            address=params.get("address"),
            added=_parse_datetime(params.get("added")),
        ) is None:
            raise ValueError("Position rejected: quality filter (accuracy or speed)")
        latest = _lookup_latest_position(device_key=device)
        return {
            "ok": True,
            "operation": operation,
            "device": latest.get("device"),
            "position": latest.get("position"),
        }
    if operation == "get_latest_position":
        device_pk = params.get("device_id")
        device_key = str(params.get("device") or "").strip()
        latest = _lookup_latest_position(device_pk=device_pk, device_key=device_key)
        return {
            "ok": True,
            "operation": operation,
            "device": latest.get("device"),
            "position": latest.get("position"),
        }
    if operation == "delete_position":
        position_id = params.get("position_id")
        if position_id in (None, ""):
            raise ValueError("position_id is required")
        deleted = mcp_delete_entity(POSITIONS, int(position_id))
        return {"ok": deleted, "operation": operation, "position_id": int(position_id), "deleted": deleted}
    if operation == "resolve_address":
        lat = params.get("lat")
        lon = params.get("lon")
        if lat is None or lon is None:
            raise ValueError("lat and lon are required")
        instance = _plugin_instance()
        if instance is None:
            raise ValueError("GpsTracker plugin not loaded")
        provider = (instance.config.get("address_provider") or "disabled").strip().lower()
        if is_provider_disabled(provider):
            return {
                "ok": True,
                "operation": operation,
                "provider": provider,
                "address": None,
                "disabled": True,
            }
        address = resolve_address(instance.config, float(lat), float(lon), instance.logger)
        return {
            "ok": True,
            "operation": operation,
            "provider": provider,
            "address": address,
            "disabled": False,
        }
    if operation == "get_history_stats":
        stats = history_ops.get_history_stats(device_id=params.get("device_id"))
        return {"ok": True, "operation": operation, **stats}
    if operation == "optimize_history":
        mode = params.get("mode")
        if not mode:
            raise ValueError("mode is required")
        result = history_ops.optimize_history(
            mode=mode,
            dry_run=params.get("dry_run", False),
            days=params.get("days"),
            distance_m=params.get("distance_m"),
            interval_minutes=params.get("interval_minutes"),
            device_id=params.get("device_id"),
        )
        return {"ok": True, "operation": operation, **result}
    raise ValueError(f"Unsupported operation: {operation}")


def mcp_descriptors() -> Tuple[list, list, list]:
    return build_plugin_mcp_descriptors(PLUGIN_NAME, mcp_capabilities())


def mcp_get_prompt(name: str, arguments: dict = None) -> dict:
    arguments = arguments or {}
    if name != _ENTITY_AUTHORING_PROMPT:
        raise ValueError(f"Unsupported prompt: {name}")
    task = str(arguments.get("task") or "").strip()
    collection = str(arguments.get("collection") or DEVICES).strip()
    if not task:
        raise ValueError("task is required")
    notes_block = "\n".join(f"- {note}" for note in _PLUGIN_NOTES)
    prompt_text = (
        "Create GpsTracker plugin entity payload by schema.\n"
        f"Plugin: {PLUGIN_NAME}\nCollection: {collection}\nTask: {task}\n\n"
        f"Plugin notes:\n{notes_block}\n\n"
        "Flow: osys_plugin_entity_schema -> validate_entity -> upsert_entity.\n"
        "For positions use invoke add_position instead of upsert_entity.\n"
        "Devices output: title, device_id (on create), linked_object.\n"
        "Locations output: title, lat, lon, range, is_home.\n"
    )
    return {"messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]}


def mcp_entity_revision(collection: str, entity_id) -> str:
    entity = mcp_get_entity(collection, entity_id)
    if collection == DEVICES:
        updated = revision_from_datetime(entity.get("updated"))
        if updated:
            return updated
        return revision_from_dict(entity, keys=["id", "title", "device_id", "linked_object", "lat", "lon"])
    if collection == LOCATIONS:
        return revision_from_dict(entity, keys=["id", "title", "lat", "lon", "range", "is_home"])
    if collection == POSITIONS:
        added = revision_from_datetime(entity.get("added"))
        if added:
            return added
        return revision_from_dict(entity, keys=["id", "device_id", "lat", "lon", "added"])
    raise ValueError(f"Unsupported collection: {collection}")


def mcp_validate_entity(collection: str, payload: dict, entity_id=None) -> dict:
    if collection == POSITIONS:
        return {"ok": False, "errors": [{"field": "collection", "message": "positions are read-only"}]}

    if not isinstance(payload, dict):
        return {"ok": False, "errors": [{"field": "_", "message": "payload must be an object"}]}

    merged = (
        _merge_device_payload(payload, entity_id=entity_id)
        if collection == DEVICES
        else _merge_location_payload(payload, entity_id=entity_id)
        if collection == LOCATIONS
        else dict(payload)
    )
    schema = mcp_entity_schema(collection)
    result = validate_entity_payload(merged, schema)
    if not result.get("ok"):
        return result

    errors = list(result.get("errors") or [])
    warnings: List[dict] = []

    readonly_fields = _DEVICE_READONLY_FIELDS if collection == DEVICES else _LOCATION_READONLY_FIELDS
    disallowed = [key for key in payload if key in readonly_fields]
    if disallowed:
        return {
            "ok": False,
            "errors": [{"field": disallowed[0], "message": "field is read-only"}],
        }

    if collection == DEVICES:
        linked_object = str(merged.get("linked_object") or "").strip()
        if linked_object and not validate_object_exists(linked_object):
            errors.append({"field": "linked_object", "message": f"Object not found: {linked_object}"})

        device_key = str(merged.get("device_id") or "").strip()
        if device_key:
            with session_scope() as session:
                duplicate = _find_device_by_key(
                    session,
                    device_key,
                    exclude_id=int(entity_id) if entity_id not in (None, "") else None,
                )
                if duplicate is not None:
                    if entity_id in (None, ""):
                        warnings.append({
                            "field": "device_id",
                            "message": (
                                f"device_id already exists: {device_key}; "
                                f"upsert without entity_id will update id={duplicate.id}"
                            ),
                        })
                    else:
                        errors.append({
                            "field": "device_id",
                            "message": f"device_id already exists: {device_key}",
                        })

        if entity_id not in (None, ""):
            with session_scope() as session:
                row = session.query(GpsDevice).filter(GpsDevice.id == int(entity_id)).one_or_none()
                if row is None:
                    errors.append({"field": "id", "message": f"device not found: {entity_id}"})

    if collection == LOCATIONS:
        range_value = merged.get("range")
        if range_value is not None:
            try:
                if float(range_value) <= 0:
                    errors.append({"field": "range", "message": "must be greater than 0"})
            except (TypeError, ValueError):
                errors.append({"field": "range", "message": "must be a number"})

        if merged.get("is_home") is True:
            with session_scope() as session:
                existing_home = session.query(GpsLocation).filter(GpsLocation.is_home.is_(True)).all()
                other_homes = [
                    row for row in existing_home
                    if entity_id in (None, "") or row.id != int(entity_id)
                ]
                if other_homes:
                    warnings.append({
                        "field": "is_home",
                        "message": (
                            f"home location already exists (id={other_homes[0].id}); "
                            "upsert will clear is_home on other locations"
                        ),
                    })

        title = str(merged.get("title") or "").strip()
        if title and entity_id in (None, ""):
            with session_scope() as session:
                duplicate = _find_location_by_title(session, title)
                if duplicate is not None:
                    warnings.append({
                        "field": "title",
                        "message": (
                            f"location title already exists: {title}; "
                            f"upsert without entity_id will update id={duplicate.id}"
                        ),
                    })

        if entity_id not in (None, ""):
            with session_scope() as session:
                row = session.query(GpsLocation).filter(GpsLocation.id == int(entity_id)).one_or_none()
                if row is None:
                    errors.append({"field": "id", "message": f"location not found: {entity_id}"})

    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    response = {"ok": True, "errors": []}
    if warnings:
        response["warnings"] = warnings
    return response
