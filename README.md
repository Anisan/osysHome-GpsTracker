# GpsTracker - GPS Tracking Module

![GpsTracker Icon](static/GpsTracker.png)

GPS tracking for osysHome: receive coordinates from phones/trackers, manage geofences, history, and map UI.

## Features

- Receive coordinates via **uLogger**, **OwnTracks**, and REST
- Devices (`GpsDevice`), geofences (`GpsLocation`), history (`GpsPosition`)
- Home / geofence matching and updates to linked objects
- Admin map: tracks, geofence edit, track-point move/delete
- History stats and cleanup tools
- Reverse geocoding providers (optional)
- MCP support (see `docs/mcp.ru.md`)

## Admin panel

Tabs: Devices, Location, Log, History, Map, Settings.

Map editing (geofences and track points) is available on the **Map** tab only. Fullscreen `/page/GpsTracker` is view-only.

Details: `docs/map-ui.md`, `docs/map-ui.ru.md`.

## Protocols and API

- uLogger: `/GpsTracker/client/index.php`
- OwnTracks: `POST /api/GpsTracker/owntracks?apikey=...`
- REST: `docs/rest-api.ru.md`

## Address detection

- `docs/address-geocoding.md`
- `docs/address-geocoding.ru.md`

## Documentation index

- `docs/index.ru.md` (Russian)

## Version

**0.7**

## Category

App

## Author

Eraser
