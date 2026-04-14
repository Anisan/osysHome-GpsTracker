# Address Detection (Reverse Geocoding)

`GpsTracker` can resolve a human-readable address from coordinates and store it in GPS log records (`gps_positions.address`).

## Settings

Address detection is configured in the module admin page:

- `Address provider` - selects the reverse-geocoding provider.

## Provider Modes

- `Disabled`
  - Reverse geocoding is turned off.
  - External/client-supplied address is ignored.
  - Address is not pushed to linked Users objects.

- `OpenStreetMap (Nominatim)` - no API key required.
- `BigDataCloud` - no API key required.
- `maps.co` - API key optional (`mapsco_api_key`).
- `Google Geocoding API` - requires `google_api_key`.
- `Yandex Geocoder` - requires `yandex_api_key`.
- `LocationIQ` - requires `locationiq_api_key`.

If a key-required provider is selected but API key is empty, module skips reverse geocoding safely (no crash).

## Priority Rules

When new coordinates are received:

1. If incoming payload already contains `address`, module keeps it as-is.
2. Otherwise, module checks configured geofences (`GpsLocation`).
3. If point is inside a geofence, geofence title is used as address.
4. If no geofence match, selected reverse-geocoding provider is used (unless disabled).

## Users Object Update Rules

- If payload contains explicit `address`, it is always pushed to linked Users object property `.address` (even when provider is `Disabled`).
- If payload does not contain explicit `address`, `.address` is pushed only when provider is not `Disabled`.

## UI Behavior

In settings form, API key input is shown only for the currently selected key-based provider.

