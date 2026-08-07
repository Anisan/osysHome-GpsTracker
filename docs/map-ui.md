# GpsTracker map UI (admin)

The **Map** tab in `Admin -> GpsTracker` shows devices, tracks, and geofences on an interactive Leaflet map.

The fullscreen page `/page/GpsTracker` is view-only (no geofence or track-point editing).

## Toolbar

- **Refresh** — reload devices, locations, and log for the selected period
- **+** — add geofence mode (admin Map tab only)
- route icon button — edit track points mode
- period filter and track visibility toggles

Changing visible tracks refits the map bounds.

Track colors come from the linked object's `color` property, or a stable palette color by `device.id`.

## Geofences on the map (admin Map tab)

1. Press **+**, then click the map to place a new zone (default radius 100 m).
2. Or click an existing circle.
3. Drag the center handle to move; drag the edge handle to resize.
4. A card next to the circle edits title / Is home and Save / Delete / Cancel.

REST: `POST /api/GpsTracker/location`, `DELETE /api/GpsTracker/location/<id>`.

## Track points (admin Map tab)

Enable track-point edit, click a point, drag to move (`PUT /api/GpsTracker/position/<id>`), or delete (`DELETE ...`).

If more than 500 visible points are loaded, edit mode is blocked — narrow the period or hide tracks.

## Confirm dialogs

Deletes use the osysHome modal confirm (`confirm` / `showConfirm`), including table tabs.
