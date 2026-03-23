# REST API GpsTracker (osysHome)

В дополнение к входящим протоколам, `GpsTracker` предоставляет REST API по префиксу:
`/api/GpsTracker`

Большинство методов требуют:
- `api key` (см. `app/api/decorators.py` в osysHome)

API key передаётся:
- `?apikey=YOURKEY` или
- заголовком `X-API-Key: YOURKEY`

Дополнительно выполнять авторизацию через сессию и cookie для этих запросов не нужно.

## Как создать API key
1. Откройте `Admin -> Users`.
2. Выберите пользователя для API-запросов.
3. Укажите значение в поле `API key` (или нажмите генерацию ключа, если такая кнопка есть в вашей сборке).
4. Сохраните изменения.

После этого используйте полученный ключ в `apikey` или `X-API-Key`.

## Устройства
- `GET /api/GpsTracker/devices` — список устройств (`GpsDevice`)
- `GET /api/GpsTracker/device/<device_id>` — получение устройства
- `POST /api/GpsTracker/device/<device_id>` — создать/обновить
  - тело: JSON с полями:
    - `id` (если передан — используется для обновления)
    - `title`
    - `linked_object`
- `DELETE /api/GpsTracker/device/<device_id>` — удалить устройство и его историю

## Геозоны (Location)
- `GET /api/GpsTracker/locations` — список геозон
- `GET /api/GpsTracker/location/<location_id>` — получить геозону
- `POST /api/GpsTracker/location` — создать/обновить
  - тело JSON:
    - `id` (опционально)
    - `title`
    - `lat`, `lon`
    - `range` (радиус в метрах)
    - `is_home` (true/false)
- `DELETE /api/GpsTracker/location/<location_id>` — удалить геозону

## Лог точек (история)
- `GET /api/GpsTracker/log`
  - параметры:
    - `start_time` — ISO datetime (строка)
    - `end_time` — ISO datetime (строка)
    - `device_id` — фильтр по `device_id`
    - `page`, `per_page` — пагинация (опционально)
    - `order_desc` — сортировка по времени (true/false)

Ответ содержит:
- `result`: список `GpsPosition`
- `total`: общее количество

## Ручная отправка координат
Для экспериментов и интеграции с собственным софтом можно отправлять координаты напрямую.

- `POST /api/GpsTracker/position`
  - тело JSON:
    - `device` — имя устройства (то же, что хранится как `GpsDevice.device_id`)
    - `lat`, `lon`
    - опционально: `alt`, `accuracy`, `speed`, `battery`, `charging`, `provider`, `address`, `added`

Также есть вариант:
- `GET /api/GpsTracker/position?device=...&lat=...&lon=...` (параметры задаются в query-string)

## Обновление/удаление точек (для опытных)
- `PUT /api/GpsTracker/position/<position_id>` — изменить `lat`/`lon`
- `DELETE /api/GpsTracker/position/<position_id>` — удалить запись

