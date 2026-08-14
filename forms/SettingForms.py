from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, SubmitField, StringField
from wtforms.validators import NumberRange, Optional


class SettingsForm(FlaskForm):
    map_provider = SelectField(
        "Map provider",
        choices=[
            ("openstreetmap", "OpenStreetMap"),
            ("carto_light", "CartoDB Positron (Light)"),
            ("carto_dark", "CartoDB Dark Matter"),
            ("opentopomap", "OpenTopoMap"),
            ("2gis", "2GIS"),
            ("google_streets", "Google Map Streets"),
            ("google_hybrid", "Google Map Hybrid"),
            ("google_satellite", "Google Map Satellite"),
            ("yandex", "Yandex"),
        ],
        validators=[Optional()],
    )
    address_provider = SelectField(
        "Address provider",
        choices=[
            ("disabled", "Disabled"),
            ("openstreetmap", "OpenStreetMap (Nominatim)"),
            ("bigdatacloud", "BigDataCloud"),
            ("mapsco", "maps.co"),
            ("google", "Google Geocoding API (API key)"),
            ("yandex", "Yandex Geocoder (API key)"),
            ("locationiq", "LocationIQ (API key)"),
        ],
        validators=[Optional()],
    )
    google_api_key = StringField("Google API key", validators=[Optional()])
    yandex_api_key = StringField("Yandex API key", validators=[Optional()])
    locationiq_api_key = StringField("LocationIQ API key", validators=[Optional()])
    mapsco_api_key = StringField("maps.co API key", validators=[Optional()])
    max_accuracy_m = IntegerField(
        "Max accuracy (m)",
        validators=[Optional(), NumberRange(min=0)],
        default=0,
    )
    max_speed_kmh = IntegerField(
        "Max speed (km/h)",
        validators=[Optional(), NumberRange(min=0)],
        default=0,
    )
    submit = SubmitField("Submit")

