# Протокол uLogger (endpoint `/GpsTracker/client/index.php`)

`GpsTracker` поддерживает приём геолокации в стиле uLogger через `POST /GpsTracker/client/index.php`.

uLogger-часть работает через `action`:
- `action=auth` — авторизация (создаёт сессию)
- `action=addtrack` — заглушка ответа (не создаёт трек в модуле)
- `action=addpos` — отправка координат

## Важно про сессию
В обработчике у uLogger сначала проверяется:
- если `action != "auth"` и в Flask-сессии нет `user`, сервер вернёт `401 Unauthorized`.

Значит, клиент uLogger должен **хранить cookie-сессию**, полученную на `action=auth`, и отправлять её в следующих запросах.

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

## Пример (curl) — uLogger

1) Авторизация (получить cookie):
```bash
curl -c cookies.txt -X POST "http://your-server/GpsTracker/client/index.php" \
  -d "action=auth&user=myuser"
```

2) Отправка координат:
```bash
curl -b cookies.txt -X POST "http://your-server/GpsTracker/client/index.php" \
  -d "action=addpos&lat=55.751244&lon=37.618423&time=1710000000&altitude=200&speed=0.1&accuracy=30&provider=gps&comment=Test%20location&battlevel=85&charging=false"
```

Ожидаемый ответ:
`{"error": false}`

## Проверка результата
После приёма:
- появится `GpsDevice` (если его ещё не было)
- появится запись в `GpsPosition`
- если устройство было привязано к объекту osysHome (`Linked object`), обновятся свойства `<object>.latlon`, `<object>.home`, `<object>.location`, `<object>.address`, `<object>.battery`, `<object>.isCharging`, `<object>.home_distance`

## Частые проблемы
- uLogger “не отправляет” — чаще всего забыли отправлять cookie после `action=auth` (сервер вернёт 401).
- Нет обновлений свойств в osysHome — почти всегда не создали свойства объекта с точными именами (см. `using-in-osyshome.ru.md`).

