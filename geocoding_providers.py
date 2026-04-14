import json
import urllib.parse
import urllib.request


_DISABLED_VALUES = ("", "none", "disabled", "off", "false", "0")


def is_provider_disabled(provider: str | None) -> bool:
    return (provider or "").strip().lower() in _DISABLED_VALUES


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "NextGetSmart/OsysHome GpsTracker (reverse-geocoding)",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8", errors="replace") or "{}")


def _reverse_geocode_openstreetmap(lat: float, lon: float) -> str | None:
    qs = urllib.parse.urlencode(
        {
            "format": "jsonv2",
            "lat": str(lat),
            "lon": str(lon),
            "zoom": "18",
            "addressdetails": "0",
        }
    )
    parsed = _fetch_json(f"https://nominatim.openstreetmap.org/reverse?{qs}")
    name = parsed.get("display_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _reverse_geocode_bigdatacloud(lat: float, lon: float) -> str | None:
    qs = urllib.parse.urlencode(
        {
            "latitude": str(lat),
            "longitude": str(lon),
            "localityLanguage": "en",
        }
    )
    parsed = _fetch_json(f"https://api.bigdatacloud.net/data/reverse-geocode-client?{qs}")
    locality = parsed.get("locality")
    city = parsed.get("city")
    principal = parsed.get("principalSubdivision")
    country = parsed.get("countryName")
    parts = [p for p in [locality, city, principal, country] if isinstance(p, str) and p.strip()]
    if parts:
        return ", ".join(dict.fromkeys([p.strip() for p in parts]))
    return None


def _reverse_geocode_mapsco(lat: float, lon: float, config: dict) -> str | None:
    api_key = (config.get("mapsco_api_key") or "").strip()
    qs = urllib.parse.urlencode({"lat": str(lat), "lon": str(lon)})
    if api_key:
        qs += "&" + urllib.parse.urlencode({"api_key": api_key})
    parsed = _fetch_json(f"https://geocode.maps.co/reverse?{qs}")
    name = parsed.get("display_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _reverse_geocode_google(lat: float, lon: float, config: dict) -> str | None:
    api_key = (config.get("google_api_key") or "").strip()
    if not api_key:
        return None
    qs = urllib.parse.urlencode({"latlng": f"{lat},{lon}", "key": api_key, "language": "en"})
    parsed = _fetch_json(f"https://maps.googleapis.com/maps/api/geocode/json?{qs}")
    results = parsed.get("results") or []
    if isinstance(results, list) and results:
        formatted = results[0].get("formatted_address")
        if isinstance(formatted, str) and formatted.strip():
            return formatted.strip()
    return None


def _reverse_geocode_yandex(lat: float, lon: float, config: dict) -> str | None:
    api_key = (config.get("yandex_api_key") or "").strip()
    if not api_key:
        return None
    qs = urllib.parse.urlencode(
        {"apikey": api_key, "geocode": f"{lon},{lat}", "format": "json", "results": "1"}
    )
    parsed = _fetch_json(f"https://geocode-maps.yandex.ru/1.x/?{qs}")
    members = parsed.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
    if isinstance(members, list) and members:
        text = (
            members[0]
            .get("GeoObject", {})
            .get("metaDataProperty", {})
            .get("GeocoderMetaData", {})
            .get("text")
        )
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _reverse_geocode_locationiq(lat: float, lon: float, config: dict) -> str | None:
    api_key = (config.get("locationiq_api_key") or "").strip()
    if not api_key:
        return None
    qs = urllib.parse.urlencode(
        {"key": api_key, "lat": str(lat), "lon": str(lon), "format": "json"}
    )
    parsed = _fetch_json(f"https://us1.locationiq.com/v1/reverse?{qs}")
    name = parsed.get("display_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def resolve_address(config: dict, lat: float, lon: float, logger=None) -> str | None:
    provider = (config.get("address_provider") or "disabled").strip().lower()
    if is_provider_disabled(provider):
        return None
    try:
        if provider in ("openstreetmap", "osm", "nominatim"):
            return _reverse_geocode_openstreetmap(lat, lon)
        if provider in ("bigdatacloud", "bdc"):
            return _reverse_geocode_bigdatacloud(lat, lon)
        if provider in ("mapsco", "maps.co", "geocodemapsco"):
            return _reverse_geocode_mapsco(lat, lon, config)
        if provider in ("google", "googlemaps"):
            return _reverse_geocode_google(lat, lon, config)
        if provider in ("yandex", "yandexgeocoder"):
            return _reverse_geocode_yandex(lat, lon, config)
        if provider in ("locationiq", "liq"):
            return _reverse_geocode_locationiq(lat, lon, config)
    except Exception as ex:
        if logger:
            logger.debug("Reverse geocode failed for provider '%s': %s", provider, ex)
    return None

