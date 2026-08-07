# MCP — GpsTracker

Плагин принимает GPS-координаты (uLogger, OwnTracks, REST), хранит устройства/геозоны/историю и обновляет свойства связанных объектов osysHome. Для runtime-операций используйте `invoke`.

## Plugin notes

- Устройство хранит внешний идентификатор в `device_id`; `lat`/`lon`/`updated` обновляются при каждой позиции (**read-only** через MCP).
- Привязка к osysHome — поле `linked_object` на устройстве. Объект должен иметь свойства: `latlon`, `location`, `home`, `address`, `home_distance`, `battery`, `isCharging`.
- Геозоны (`locations`) задают центр + радиус в метрах. Одна зона с `is_home=true` — «дом».
- История позиций **только для чтения** через `upsert_entity`; добавление — `add_position`, удаление — `delete_position`.
- `add_position` выполняет тот же pipeline, что REST/OwnTracks: геозоны, reverse geocoding, обновление `linked_object`.
- `address_provider` в конфиге управляет обратным геокодированием.
- Передайте `address` в `add_position`, чтобы пропустить geocoding для точки.

## Collections

| ID | binding_mode | writable | writable_fields | list_filters |
|----|--------------|----------|-----------------|--------------|
| `devices` | `object` | yes | `title`, `device_id`, `linked_object` | `query`, `linked_object`, `has_linked_object` |
| `locations` | `none` | yes | `title`, `lat`, `lon`, `range`, `is_home` | `query`, `is_home` |
| `positions` | `none` | no | — | `device_id`, `query`, `start_time`, `end_time`, `order_desc` |

## Операции (invoke)

| operation | Описание |
|-----------|----------|
| `add_position` | Добавить точку (`device`, `lat`, `lon`, опционально `address`, `battery`, …) |
| `get_latest_position` | Последняя позиция (`device_id` или `device`) |
| `delete_position` | Удалить запись истории (`position_id`) |
| `resolve_address` | Проверить reverse geocoding для `lat`/`lon` с текущим `address_provider` |

## Примеры

### Создать устройство с привязкой к объекту

```json
{
  "plugin": "GpsTracker",
  "action": "upsert_entity",
  "args": {
    "collection": "devices",
    "payload": {
      "title": "Телефон Ивана",
      "device_id": "ivan_phone",
      "linked_object": "JohnPhone"
    }
  }
}
```

### Создать геозону «дом»

```json
{
  "plugin": "GpsTracker",
  "action": "upsert_entity",
  "args": {
    "collection": "locations",
    "payload": {
      "title": "Дом",
      "lat": 55.751244,
      "lon": 37.618423,
      "range": 200,
      "is_home": true
    }
  }
}
```

### Добавить позицию вручную

```json
{
  "plugin": "GpsTracker",
  "action": "invoke",
  "args": {
    "operation": "add_position",
    "params": {
      "device": "ivan_phone",
      "lat": 55.751,
      "lon": 37.618,
      "battery": 87,
      "charging": false
    }
  }
}
```

### Последняя позиция устройства

```json
{
  "plugin": "GpsTracker",
  "action": "invoke",
  "args": {
    "operation": "get_latest_position",
    "params": {"device": "ivan_phone"}
  }
}
```

### История позиций за период

```json
{
  "plugin": "GpsTracker",
  "action": "list_entities",
  "args": {
    "collection": "positions",
    "device_id": 1,
    "start_time": "2026-07-01 00:00:00",
    "end_time": "2026-07-13 23:59:59",
    "order_desc": true,
    "limit": 50
  }
}
```

### Проверить geocoding

```json
{
  "plugin": "GpsTracker",
  "action": "invoke",
  "args": {
    "operation": "resolve_address",
    "params": {"lat": 55.751, "lon": 37.618}
  }
}
```
