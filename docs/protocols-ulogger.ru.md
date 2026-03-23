# Протокол uLogger (endpoint `/GpsTracker/client/index.php`)

`GpsTracker` поддерживает приём геолокации в стиле uLogger через `POST /GpsTracker/client/index.php`.

uLogger-часть работает через `action`:
- `action=auth` — авторизация (создаёт сессию, legacy-механизм)
- `action=addtrack` — заглушка ответа (не создаёт трек в модуле)
- `action=addpos` — отправка координат

## Важно
Механизм `action=auth` + сессия относится к legacy-совместимости uLogger.
Для новых интеграций рекомендуется API key (см. `rest-api.ru.md`) — без отдельной авторизации и без cookie.

## Как устроен идентификатор устройства
На `addpos` сервер строит имя устройства так:
`device = <user из action=auth> + "_ulogger"`

Дальше этот `device` используется для поиска/создания записи `GpsDevice` и для дальнейшей записи истории точек.

## Поля запроса `addpos`
Сервер читает (как строковые параметры формы):
- `lat` — широта
- `lon` — долгота
- `time` — Unix timestamp (секунды)
- `altitude` — высота (float, опционально)
- `speed` — скорость (float, опционально)
- `accuracy` — точность (float, опционально)
- `provider` — провайдер (строка, опционально)
- `comment` — используется как “адрес”:
  - если устройство не попало ни в одну геозону, то `<object>.address` станет `comment`
  - если попало в геозону, `address` перезапишется названием геозоны
- `battlevel` — батарея (float/строка, опционально)
- `charging` — в виде строки `"true"` или `"false"` (определяет `<object>.isCharging`)

## Рекомендуемый способ отправки без cookie
Для новых интеграций используйте API key и REST endpoint (без `action=auth` и без сохранения cookie):

```bash
curl -X POST "http://your-server/api/GpsTracker/position?apikey=YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "device": "myuser_ulogger",
    "lat": 55.751244,
    "lon": 37.618423,
    "added": "2026-03-23T10:15:00",
    "alt": 200,
    "speed": 0.1,
    "accuracy": 30,
    "provider": "gps",
    "address": "Test location",
    "battery": 85,
    "charging": false
  }'
```

Ожидаемый ответ:
`{"error": false}`

## Проверка результата
После приёма:
- появится `GpsDevice` (если его ещё не было)
- появится запись в `GpsPosition`
- если устройство было привязано к объекту osysHome (`Linked object`), обновятся свойства `<object>.latlon`, `<object>.home`, `<object>.location`, `<object>.address`, `<object>.battery`, `<object>.isCharging`, `<object>.home_distance`

## Частые проблемы
- `401 Unauthorized` — обычно не передан/неверен `API key`.
- Нет обновлений свойств в osysHome — почти всегда не создали свойства объекта с точными именами (см. `using-in-osyshome.ru.md`).

