# Протокол OwnTracks (endpoint `/api/GpsTracker/owntracks`)

`GpsTracker` умеет принимать события OwnTracks через `POST /api/GpsTracker/owntracks`.

Эндпоинт поддерживает **входящие location** и дополнительно умеет отвечать “друзьям” (другим трекерам), чтобы OwnTracks могли обмениваться статусами.

## Аутентификация (для REST-части)
Маршрут `owntracks` обёрнут декораторами osysHome API:
- нужен `api key`

API key можно передать одним из способов:
- как параметр URL: `?apikey=YOURKEY`
- или заголовком: `X-API-Key: YOURKEY`

## Формат JSON запроса
Ожидается JSON с полем `"_type" == "location"`.

Минимально используемые поля:
- `tid` — идентификатор трекера (используется как `GpsDevice.device_id`)
- `lat`, `lon` — координаты
- `alt` — высота
- `acc` — точность
- `vel` — скорость
- `tst` — время (Unix timestamp секунд)
- `batt` — батарея (float, опционально)
- `bs` — статус зарядки:
  - `bs == 2` -> `charging = true`
  - иначе -> `charging = false`

## Пример (curl) — OwnTracks location
```bash
curl -X POST "http://your-server/api/GpsTracker/owntracks?apikey=YOURKEY" \
  -H "Content-Type: application/json" \
  -d '{
    "_type": "location",
    "tid": "john",
    "lat": 55.751244,
    "lon": 37.618423,
    "alt": 200,
    "acc": 30,
    "vel": 0.1,
    "tst": 1710000000,
    "batt": 82,
    "bs": 1
  }'
```

## Что вернёт сервер
Ответ — JSON-массив `[]` (иногда с элементами), содержащий:
- `_type: "location"` для “друзей” (других устройств, которые в БД имеют `linked_object`)
- опционально `_type: "card"` с карточкой (имя/аватар) — но **не чаще чем раз в час на один `tid`**

### Что нужно, чтобы “друзья” работали
Для устройства, которое вы хотите получать как “card/location”, у него должно быть задано `Linked object` в GpsTracker:
- модуль берёт `dev.linked_object` и подставляет его в поле `tid` ответа OwnTracks
- имя берётся из `obj.description`
- аватар берётся из `obj.image` (если задано)

## Отладка
- Если приходит `401`, значит проблема с API key.
- Если “друзья” пустые — скорее всего, у других `GpsDevice` не задан `linked_object`.

