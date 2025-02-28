from flask import render_template, request, jsonify
import datetime
from app.core.main.BasePlugin import BasePlugin
from app.api import api
from app.database import session_scope
from app.core.lib.object import updatePropertyThread
from plugins.GpsTracker.utils import calculate_distance, in_location
from plugins.GpsTracker.models.GpsDevice import GpsDevice
from plugins.GpsTracker.models.GpsLocation import GpsLocation
from plugins.GpsTracker.models.GpsPosition import GpsPosition

class GpsTracker(BasePlugin):

    def __init__(self,app):
        super().__init__(app,__name__)
        self.title = "GPS tracker"
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
        return render_template('gpslogger.html')

    def route_index(self):
        '''Support ulogger'''
        @self.blueprint.route("/client/index.php",methods=['POST'])
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
                comment = request.form.get('comment')
                # image_meta = request.form.get('image')
                # track_id = request.form.get('trackid')
                battlevel = request.form.get('battlevel')
                charging = request.form.get('charging')
                charging = True if charging == 'true' else False

                device = session['user'] + "_ulogger"

                added = datetime.datetime.fromtimestamp(timestamp)

                self.addGpsPosition(device,lat,lon,altitude,accuracy,speed,battlevel,charging,provider,comment,added)
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
            device_rec.updated = added if added else datetime.datetime.now()

            home_location = session.query(GpsLocation).where(GpsLocation.is_home).one_or_none()
            distance = None
            is_home = 0
            if home_location:
                distance = calculate_distance(lat, lon, home_location.lat, home_location.lon)
                if distance < home_location.range:
                    is_home = 1

            gps_position = GpsPosition(
                added=added if added else datetime.datetime.now(),
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

            current_location = None
            locations = session.query(GpsLocation).all()
            for location in locations:
                if in_location(lat,lon, location.lat, location.lon, location.range):
                    current_location = location.title
                    break

            if device_rec.linked_object:
                updatePropertyThread(device_rec.linked_object + ".latlon", f'{lat},{lon}', source=self.name)
                # updatePropertyThread(device_rec.linked_object + ".lon", lon)
                # updatePropertyThread(device_rec.linked_object + ".alt", alt)
                updatePropertyThread(device_rec.linked_object + ".location", current_location, source=self.name)
                updatePropertyThread(device_rec.linked_object + ".home", is_home, source=self.name)
                updatePropertyThread(device_rec.linked_object + ".address", address, source=self.name)
                updatePropertyThread(device_rec.linked_object + ".home_distance", distance, source=self.name)
                updatePropertyThread(device_rec.linked_object + ".battery", battery, source=self.name)
                updatePropertyThread(device_rec.linked_object + ".isCharging", charging, source=self.name)

            return gps_position
