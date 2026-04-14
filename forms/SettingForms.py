from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField, StringField
from wtforms.validators import Optional


class SettingsForm(FlaskForm):
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
    submit = SubmitField("Submit")

