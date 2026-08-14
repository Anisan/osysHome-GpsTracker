from flask import request
from flask_restx import Namespace, Resource,fields, reqparse
from sqlalchemy import delete, desc
from app.api.decorators import api_key_required
from app.authentication.handlers import handle_user_required
from app.api.models import model_404, model_result
from app.database import row2dict, session_scope, convert_local_to_utc, convert_utc_to_local, get_user_timezone, get_now_to_utc
from app.core.lib.object import getProperty, getObject
from plugins.GpsTracker import GpsTracker
from plugins.GpsTracker import history_ops
from plugins.GpsTracker.models.GpsDevice import GpsDevice
from plugins.GpsTracker.models.GpsLocation import GpsLocation
from plugins.GpsTracker.models.GpsPosition import GpsPosition
import datetime
import time
import os
import base64
from app.extensions import cache

_api_ns = Namespace(name="GpsTracker", description="GpsTracker namespace", validate=True)

response_result = _api_ns.model("Result", model_result)
response_404 = _api_ns.model("Error", model_404)

_instance: GpsTracker = None


def create_api_ns(instance:GpsTracker):
    global _instance
    _instance = instance
    return _api_ns


def _ensure_local_datetimes(data: dict) -> dict:
    """Ensure datetime fields are in user-local time (row2dict skips if profile timezone is empty)."""
    from flask_login import current_user

    if getattr(current_user, "timezone", None):
        return data
    for key, value in list(data.items()):
        if isinstance(value, datetime.datetime):
            data[key] = convert_utc_to_local(value)
    return data


def _gps_row2dict(row) -> dict:
    return _ensure_local_datetimes(row2dict(row))


def _parse_filter_time(value: str):
    """Parse UI datetime string (user wall clock) to UTC for DB filtering."""
    if not value:
        return None
    value = value.strip()
    if len(value) >= 13 and value[11:13] == "24":
        value = value[:11] + "00" + value[13:]
    for fmt, size in (("%Y-%m-%d %H:%M:%S.%f", 23), ("%Y-%m-%d %H:%M:%S", 19)):
        try:
            parsed = datetime.datetime.strptime(value[:size], fmt)
            return convert_local_to_utc(parsed, timezone=get_user_timezone())
        except ValueError:
            continue
    raise ValueError(f"Invalid datetime filter: {value}")


def _period_bounds(period: str):
    """Return UTC start/end for named periods using the authenticated user's timezone."""
    period = (period or "").strip().lower()
    tz = get_user_timezone()
    now_local = convert_utc_to_local(get_now_to_utc(), tz)
    today = now_local.date()

    if period == "today":
        start_local = datetime.datetime.combine(today, datetime.time.min)
        end_local = datetime.datetime.combine(today, datetime.time(23, 59, 59))
    elif period == "yesterday":
        day = today - datetime.timedelta(days=1)
        start_local = datetime.datetime.combine(day, datetime.time.min)
        end_local = datetime.datetime.combine(day, datetime.time(23, 59, 59))
    elif period == "last24h":
        end_local = now_local.replace(microsecond=0)
        start_local = end_local - datetime.timedelta(hours=24)
    elif period == "week":
        end_local = now_local.replace(microsecond=0)
        start_local = end_local - datetime.timedelta(days=7)
    else:
        raise ValueError(f"Unsupported period: {period}")

    return (
        convert_local_to_utc(start_local, timezone=tz),
        convert_local_to_utc(end_local, timezone=tz),
    )


@_api_ns.route("/devices", endpoint="gpstracker_devices")
class GetDevices(Resource):
    @api_key_required
    @handle_user_required
    def get(self):
        with session_scope() as session:
            devices = session.query(GpsDevice).all()
            result = [_gps_row2dict(device) for device in devices]
            for item in result:
                if item['linked_object']:
                    item['user'] = getProperty(item['linked_object'] + ".description")
                    item['avatar'] = getProperty(item['linked_object'] + ".image")
                    item['color'] = getProperty(item['linked_object'] + ".color")
                    item['home_distance'] = getProperty(item['linked_object'] + ".home_distance")
            return {"success": True, "result": result}, 200

@_api_ns.route("/device/<device_id>", endpoint="gpstracker_device")
class EndpointGpsDevice(Resource):
    @api_key_required
    @handle_user_required
    def get(self,device_id: int):
        """ Get device """
        with session_scope() as session:
            device = session.query(GpsDevice).filter(GpsDevice.id == device_id).one_or_none()
            if device:
                result = _gps_row2dict(device)
                return {"success": True, "result": result}, 200
            return {"success": False, "msg": "Task not found"}, 404
    @api_key_required
    @handle_user_required
    def post(self,device_id:int):
        """ Create/update device """
        with session_scope() as session:
            data = request.get_json()
            if data["id"]:
                device = session.query(GpsDevice).filter(GpsDevice.id == device_id).one()
            else:
                device = GpsDevice()
                session.add(device)
            device.title = data['title']
            device.linked_object = data['linked_object']
            session.commit()
            return {"success": True}, 200
    @api_key_required
    @handle_user_required
    def delete(self,device_id:int):
        """ Delete device """
        with session_scope() as session:
            sql = delete(GpsPosition).where(GpsPosition.device_id == int(device_id))
            session.execute(sql)
            sql = delete(GpsDevice).where(GpsDevice.id == int(device_id))
            session.execute(sql)
            session.commit()
            return {"success": True}, 200

@_api_ns.route("/locations", endpoint="gpstracker_locations")
class GetLocations(Resource):
    @api_key_required
    @handle_user_required
    def get(self):
        with session_scope() as session:
            locations = session.query(GpsLocation).all()
            result = [_gps_row2dict(location) for location in locations]
            return {"success": True, "result": result}, 200

@_api_ns.route('/location', methods=['POST'])
@_api_ns.route("/location/<location_id>", methods=['GET','DELETE'])
class EndpointGpsLocation(Resource):
    @api_key_required
    @handle_user_required
    def get(self,location_id: int):
        """ Get location """
        with session_scope() as session:
            location = session.query(GpsLocation).filter(GpsLocation.id == location_id).one_or_none()
            if location:
                result = _gps_row2dict(location)
                return {"success": True, "result": result}, 200
            return {"success": False, "msg": "Task not found"}, 404
    @api_key_required
    @handle_user_required
    def post(self):
        """ Create/update location """
        with session_scope() as session:
            data = request.get_json()
            if data.get("id",None):
                location = session.query(GpsLocation).filter(GpsLocation.id == data["id"]).one()
            else:
                location = GpsLocation()
                session.add(location)
            location.title = data.get('title',None)
            location.lat = data.get('lat',None)
            location.lon = data.get('lon',None)
            location.range = data.get('range',None)
            location.is_home = data.get('is_home',False)
            session.commit()
            return {"success": True}, 200
    @api_key_required
    @handle_user_required
    def delete(self,location_id:int):
        """ Delete location """
        with session_scope() as session:
            sql = delete(GpsLocation).where(GpsLocation.id == int(location_id))
            session.execute(sql)
            session.commit()
            return {"success": True}, 200


_parser = _api_ns.parser()
_parser.add_argument('start_time', type=str, help='Start time for filtering logs in ISO format')
_parser.add_argument('end_time', type=str, help='End time for filtering logs in ISO format')
_parser.add_argument('device_id', type=str, help='Device ID to filter logs')
_parser.add_argument('page', type=int, default=1, help='Page number for pagination (default is 1)')
_parser.add_argument('per_page', type=int, help='Number of items per page (default is 10)')
_parser.add_argument('order_desc', type=bool, help='Whether to order results in descending order')
_parser.add_argument('period', type=str, help='Named period: today, yesterday, last24h, week')


@_api_ns.route("/log", endpoint="gpstracker_logs")
class GetLogs(Resource):
    @api_key_required
    @handle_user_required
    @_api_ns.doc(params={
        'start_time': 'Start time for filtering logs in ISO format',
        'end_time': 'End time for filtering logs in ISO format',
        'device_id': 'Device ID to filter logs',
        'page': 'Page number for pagination',
        'per_page': 'Number of items per page',
        'order_desc': 'Whether to order results in descending order',
        'period': 'Named period: today, yesterday, last24h, week',
    })
    def get(self):
        args = _parser.parse_args()

        start_time = args.get('start_time')
        end_time = args.get('end_time')
        period = args.get('period')
        device_id = args.get('device_id')
        page = args.get('page', None)
        per_page = args.get('per_page', None)

        with session_scope() as session:
            query = session.query(GpsPosition)

            if period:
                try:
                    start_time, end_time = _period_bounds(period)
                except ValueError as exc:
                    return {"success": False, "error": str(exc)}, 400
            else:
                if start_time:
                    try:
                        start_time = _parse_filter_time(start_time)
                    except ValueError as exc:
                        return {"success": False, "error": str(exc)}, 400
                if end_time:
                    try:
                        end_time = _parse_filter_time(end_time)
                    except ValueError as exc:
                        return {"success": False, "error": str(exc)}, 400

            if start_time:
                query = query.filter(GpsPosition.added >= start_time)
            if end_time:
                query = query.filter(GpsPosition.added <= end_time)
            if device_id:
                query = query.filter(GpsPosition.device_id == device_id)

            # Пагинация
            total = query.count()  # Общее количество записей

            order_desc = args.get('order_desc', False)
            if order_desc:
                query = query.order_by(desc(GpsPosition.added))
            else:
                query = query.order_by(GpsPosition.added)
            if per_page and page:
                logs = query.offset((page - 1) * per_page).limit(per_page).all()
            else:
                logs = query.all()

            result = [_gps_row2dict(log) for log in logs]
            data = {
                "success": True,
                "result": result,
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": ((total + per_page - 1) // per_page) if per_page else None
            }

            return data, 200


@_api_ns.route("/history/stats", endpoint="gpstracker_history_stats")
class GpsHistoryStatsResource(Resource):
    stats_parser = reqparse.RequestParser()
    stats_parser.add_argument("device_id", type=int, required=False, location="args")

    @api_key_required
    @handle_user_required
    @_api_ns.expect(stats_parser)
    def get(self):
        """History statistics and optimization suggestions"""
        args = self.stats_parser.parse_args()
        result = history_ops.get_history_stats(device_id=args.get("device_id"))
        return {"success": True, "result": result}, 200


optimize_history_model = _api_ns.model(
    "GpsHistoryOptimize",
    {
        "mode": fields.String(
            required=True,
            description="older_than | deduplicate | thin_stationary | clear_device",
        ),
        "dry_run": fields.Boolean(required=False, default=False),
        "days": fields.Integer(required=False, description="For older_than"),
        "distance_m": fields.Float(required=False),
        "interval_minutes": fields.Integer(required=False),
        "device_id": fields.Integer(required=False),
    },
)


@_api_ns.route("/history/optimize", endpoint="gpstracker_history_optimize")
class GpsHistoryOptimizeResource(Resource):
    @api_key_required
    @handle_user_required
    @_api_ns.expect(optimize_history_model)
    def post(self):
        """Run history optimization (supports dry_run preview)"""
        payload = request.get_json(silent=True) or {}
        mode = payload.get("mode")
        if not mode:
            return {"success": False, "error": "mode is required"}, 400
        try:
            result = history_ops.optimize_history(
                mode=mode,
                dry_run=payload.get("dry_run", False),
                days=payload.get("days"),
                distance_m=payload.get("distance_m"),
                interval_minutes=payload.get("interval_minutes"),
                device_id=payload.get("device_id"),
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}, 400
        return {"success": True, "result": result}, 200


gps_position_model = _api_ns.model('GpsPosition', {
    'device': fields.String(required=True, description='Device name'),
    'lat': fields.Float(required=True, description='Latitude'),
    'lon': fields.Float(required=True, description='Longitude'),
    'alt': fields.Float(description='Altitude'),
    'accuracy': fields.Float(description='Accuracy'),
    'peed': fields.Float(description='Speed'),
    'battery': fields.Float(description='Battery level'),
    'charging': fields.Boolean(description='Charging status'),
    'provider': fields.String(description='Provider'),
    'address': fields.String(description='Address'),
    'added': fields.DateTime(description='Timestamp')
})

@_api_ns.route("/position", methods=['GET','POST'])
@_api_ns.route("/position/<position_id>", methods=['PUT','DELETE'])
class GpsPositionResource(Resource):
    get_parser = reqparse.RequestParser()
    get_parser.add_argument('device', type=str, required=True, location='args')
    get_parser.add_argument('lat', type=float, required=True, location='args')
    get_parser.add_argument('lon', type=float, required=True, location='args')
    get_parser.add_argument('alt', type=float, required=False, location='args')
    get_parser.add_argument('accuracy', type=float, required=False, location='args')
    get_parser.add_argument('speed', type=float, required=False, location='args')
    get_parser.add_argument('battery', type=float, required=False, location='args')
    get_parser.add_argument('charging', type=bool, required=False, location='args')
    get_parser.add_argument('provider', type=str, required=False, location='args')
    get_parser.add_argument('address', type=str, required=False, location='args')
    get_parser.add_argument('added', type=str, required=False, location='args')

    @_api_ns.expect(get_parser)
    @api_key_required
    @handle_user_required
    def get(self):
        """ Save GPS position """
        args = self.get_parser.parse_args()
        if _instance.addGpsPosition(**args) is None:
            return {'success': False, 'msg': 'Position rejected by quality filter'}, 200
        return {'success': True}, 200

    @_api_ns.expect(gps_position_model)
    @api_key_required
    @handle_user_required
    def post(self):
        """ Save GPS position """
        data = request.get_json()
        device_name = data.get('device')
        lat = data.get('lat')
        lon = data.get('lon')
        alt = data.get('alt')
        accuracy = data.get('accuracy')
        speed = data.get('speed')
        battery = data.get('battery')
        charging = data.get('charging')
        provider = data.get('provider')
        address = data.get('address')
        added = data.get('added')

        if _instance.addGpsPosition(
            device=device_name,
            lat=lat,
            lon=lon,
            alt=alt,
            accuracy=accuracy,
            speed=speed,
            battery=battery,
            charging=charging,
            provider=provider,
            address=address,
            added=added
        ) is None:
            return {'success': False, 'msg': 'Position rejected by quality filter'}, 200

        return {'success': True}, 201

    @api_key_required
    @handle_user_required
    def put(self,position_id:int):
        """ Delete position """
        with session_scope() as session:
            pos = session.query(GpsPosition).where(GpsPosition.id == int(position_id)).one_or_none()
            if pos:
                data = request.get_json()
                if 'lat' in data:
                    pos.lat = data['lat']
                if 'lng' in data:
                    pos.lon = data['lng']
                elif 'lon' in data:
                    pos.lon = data['lon']
                session.commit()
                return {"success": True}, 200
            return {"success": False}, 404

    @api_key_required
    @handle_user_required
    def delete(self,position_id:int):
        """ Delete position """
        with session_scope() as session:
            sql = delete(GpsPosition).where(GpsPosition.id == int(position_id))
            session.execute(sql)
            session.commit()
            return {"success": True}, 200

@_api_ns.route('/owntracks', methods=['POST'])
class OwnTracks(Resource):
    @api_key_required
    @handle_user_required
    def post(self):
        # Обработка входящих данных от Owntracks
        data = request.get_json()
        _instance.logger.debug(data)
        if not data:
            return {'error': 'No JSON data provided'}, 400

        required_fields = {'_type'}
        if not required_fields.issubset(data.keys()):
            return {'error': 'Missing required fields'}, 400

        result = []

        if data["_type"] == 'location':
            # store information from given datapoint
            _instance.addGpsPosition(
                device=data["tid"],
                lat=data["lat"],
                lon=data["lon"],
                alt=data["alt"],
                accuracy=data["acc"],
                speed=data["vel"],
                battery=data["batt"],
                charging=data["bs"] == 2,
                provider='owntracks',
                added=datetime.datetime.fromtimestamp(data["tst"], tz=datetime.timezone.utc).replace(tzinfo=None)
            )
            current_time = time.time()
            last_execution = cache.get("gps_ls_" + data["tid"])

            # send friends
            with session_scope() as session:
                devs = session.query(GpsDevice).filter(
                    GpsDevice.device_id != data["tid"],
                    GpsDevice.linked_object.isnot(None)
                ).all()
                for dev in devs:
                    last_location = session.query(GpsPosition).filter(GpsPosition.device_id == dev.id).order_by(desc(GpsPosition.added)).first()

                    if last_location:
                        location = {
                            "_type":"location",
                            "tid":dev.linked_object,
                            "lat":last_location.lat,
                            "lon":last_location.lon,
                            "alt":last_location.alt,
                            "batt":last_location.battery,
                            "bs": "2" if last_location.charging else "1",
                            "vel":last_location.speed,
                            "acc":last_location.accuracy,
                            "tst":int(convert_utc_to_local(last_location.added).timestamp())
                        }

                        result.append(location)

                        # Check if we need to include card info (once per hour)
                        try:
                            if last_execution is None or current_time - last_execution >= 3600:  # 3600 seconds = 1 hour
                                obj = getObject(dev.linked_object)

                                card = {
                                    '_type': 'card',
                                    'tid': dev.linked_object,
                                    'name': obj.description,
                                }
                                img = getProperty(dev.linked_object + ".image")
                                if img is None:
                                    continue
                                path_image = "/opt/osyshome" + img
                                if os.path.isfile(path_image):
                                    with open(path_image, "rb") as image_file:
                                        card['face'] = base64.b64encode(image_file.read()).decode('utf-8')

                                result.append(card)
                        except Exception as ex:
                            _instance.logger.exception(ex)
                # Update last execution time
                cache.set("gps_ls_" + data["tid"], current_time, timeout=0)

        return result, 200
