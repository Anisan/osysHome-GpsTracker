from flask import render_template, request, jsonify, redirect
import datetime
from app.core.main.BasePlugin import BasePlugin
from app.api import api
from app.database import session_scope, get_now_to_utc
from app.core.lib.object import updatePropertyThread
from plugins.GpsTracker.utils import calculate_distance, in_location
from plugins.GpsTracker.geocoding_providers import resolve_address, is_provider_disabled
from plugins.GpsTracker.models.GpsDevice import GpsDevice
from plugins.GpsTracker.models.GpsLocation import GpsLocation
from plugins.GpsTracker.models.GpsPosition import GpsPosition
from plugins.GpsTracker.forms.SettingForms import SettingsForm
from app.authentication.handlers import public_endpoint

class GpsTracker(BasePlugin):

    def __init__(self,app):
        super().__init__(app,__name__)
        self.title = "GpsTracker"
        self.description = """GPS tracker"""
        self.category = "App"
        self.version = "0.1"
        self.author = "Eraser"

        from plugins.GpsTracker.api import create_api_ns
        api_ns = create_api_ns(self)
        api.add_namespace(api_ns, path="/GpsTracker")

    def initialization(self):
        pass

    def admin(self, request):
        settings = SettingsForm()

        if request.method == "GET":
            settings.map_provider.data = self._get_map_provider()
            settings.address_provider.data = self.config.get("address_provider", "disabled")
            settings.google_api_key.data = self.config.get("google_api_key", "")
            settings.yandex_api_key.data = self.config.get("yandex_api_key", "")
            settings.locationiq_api_key.data = self.config.get("locationiq_api_key", "")
            settings.mapsco_api_key.data = self.config.get("mapsco_api_key", "")
        else:
            if settings.validate_on_submit():
                self.config["map_provider"] = settings.map_provider.data or "openstreetmap"
                self.config["address_provider"] = settings.address_provider.data or "disabled"
                self.config["google_api_key"] = (settings.google_api_key.data or "").strip()
                self.config["yandex_api_key"] = (settings.yandex_api_key.data or "").strip()
                self.config["locationiq_api_key"] = (settings.locationiq_api_key.data or "").strip()
                self.config["mapsco_api_key"] = (settings.mapsco_api_key.data or "").strip()
                self.saveConfig()
                return redirect("GpsTracker")

        return self.render("gpslogger.html", {"form": settings})

    def _get_map_provider(self):
        return (self.config.get("map_provider") or "openstreetmap").strip().lower()

    def route_index(self):
        '''Support ulogger'''
        @self.blueprint.route("/client/index.php",methods=['POST'])
        @public_endpoint
        def index_ulogger():
            def castFloat(arg):
                if arg:
                    return float(arg)
                return None
            from flask import session
            action = request.form.get('action',None)
            if action != 'auth' and session.get('user',None) is None:
                response = {
                    "error": True,
                    "message":"Unauthorized"
                }
                return jsonify(response), 401
            if action == "auth":
                user = request.form.get('user',None)
                # password = request.form.get('pass',None)
                response = {"error": False}
                session['user'] = user
                return jsonify(response), 200
            if action == 'addtrack':
                response = {
                    "error": False,
                    "trackid": 12345
                }
                return jsonify(response), 200
            if action == "addpos":
                lat = castFloat(request.form.get('lat'))
                lon = castFloat(request.form.get('lon'))
                timestamp = int(request.form.get('time'))
                altitude = castFloat(request.form.get('altitude'))
                speed = castFloat(request.form.get('speed'))
                # bearing = request.form.get('bearing')
                accuracy = castFloat(request.form.get('accuracy'))
                provider = request.form.get('provider')
                # comment = request.form.get('comment')
                # image_meta = request.form.get('image')
                # track_id = request.form.get('trackid')
                battlevel = request.form.get('battlevel')
                charging = request.form.get('charging')
                charging = True if charging == 'true' else False

                device = session['user'] + "_ulogger"

                added = datetime.datetime.fromtimestamp(timestamp)

                self.addGpsPosition(
                    device=device,
                    lat=lat,
                    lon=lon,
                    alt=altitude,
                    accuracy=accuracy,
                    speed=speed,
                    battery=battlevel,
                    charging=charging,
                    provider=provider,
                    address=None,
                    added=added,
                )
                response = {"error": False}
                return jsonify(response), 200

    def addGpsPosition(self, device:str, lat:float, lon:float, alt:float = None, accuracy:float = None, speed:float = None, battery:float = None, charging:bool = None, provider:str=None, address:str = None, added:datetime = None):
        with session_scope() as session:
            device_rec = session.query(GpsDevice).where(GpsDevice.device_id == device).one_or_none()
            if not device_rec:
                device_rec = GpsDevice(
                    title="Device - " + device,
                    device_id=device
                )
                session.add(device_rec)
                session.commit()

            device_rec.lat = lat
            device_rec.lon = lon
            device_rec.updated = added if added else get_now_to_utc()

            home_location = (
                session.query(GpsLocation)
                .where(GpsLocation.is_home)
                .order_by(GpsLocation.id)
                .first()
            )
            distance = None
            is_home = 0
            if home_location:
                distance = calculate_distance(lat, lon, home_location.lat, home_location.lon)
                if distance < home_location.range:
                    is_home = 1

            current_location = None
            locations = session.query(GpsLocation).all()
            for location in locations:
                if in_location(lat,lon, location.lat, location.lon, location.range):
                    current_location = location.title
                    break

            # If address comes from payload, keep it as-is and skip reverse-geocoding.
            incoming_address = address.strip() if isinstance(address, str) else address
            has_incoming_address = incoming_address not in (None, "")

            # Determine address from geofences or reverse-geocoding provider only when
            # caller didn't provide address explicitly.
            address_provider = (self.config.get("address_provider") or "disabled").strip().lower()
            if has_incoming_address:
                address = incoming_address
            elif current_location is not None:
                address = current_location
            elif is_provider_disabled(address_provider):
                address = None
            else:
                address = resolve_address(self.config, lat, lon, self.logger)

            gps_position = GpsPosition(
                added=added if added else get_now_to_utc(),
                device_id=device_rec.id,
                lat=lat,
                lon=lon,
                alt=alt,
                accuracy=accuracy,
                speed=speed,
                battery=battery,
                charging=charging,
                provider=provider,
                address=address
            )
            session.add(gps_position)
            session.commit()

            if device_rec.linked_object:
                address_provider = (self.config.get("address_provider") or "disabled").strip().lower()
                should_push_address = not is_provider_disabled(address_provider)
                updatePropertyThread(device_rec.linked_object + ".latlon", f'{lat},{lon}', source=self.name)
                # updatePropertyThread(device_rec.linked_object + ".lon", lon)
                # updatePropertyThread(device_rec.linked_object + ".alt", alt)
                updatePropertyThread(device_rec.linked_object + ".location", current_location, source=self.name)
                updatePropertyThread(device_rec.linked_object + ".home", is_home, source=self.name)
                if should_push_address or has_incoming_address:
                    updatePropertyThread(device_rec.linked_object + ".address", address, source=self.name)
                updatePropertyThread(device_rec.linked_object + ".home_distance", distance, source=self.name)
                updatePropertyThread(device_rec.linked_object + ".battery", battery, source=self.name)
                updatePropertyThread(device_rec.linked_object + ".isCharging", charging, source=self.name)

            return gps_position

    def changeObject(self, event, object_name, property_name, method_name, new_value):
        with session_scope() as session:
            if property_name is None and method_name is None:
                devices = session.query(GpsDevice).filter(GpsDevice.linked_object == object_name).all()
                for device in devices:
                    device.linked_object = new_value
            session.commit()
