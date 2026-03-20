# Примеры подключения и сценарии

Ниже — несколько “рабочих” сценариев, которые помогают понять, как именно связать GpsTracker с вашими устройствами.

## Сценарий 1 (для новичка): телефон через uLogger
Цель: чтобы osysHome получал координаты и обновлял свойства объекта.

1. В `Admin -> Objects` создайте объект, например: `JohnPhone`.
2. Добавьте на объект свойства:
   - `latlon`, `location`, `home`, `address`, `home_distance`, `battery`, `isCharging`
3. В `Admin -> GpsTracker`:
   - `Devices -> Add`:
     - `Title`: например `JohnPhone`
     - `Linked object`: `JohnPhone`
   - `Location -> Add`:
     - сделайте одну запись с `Is home = true` (это “дом”)
     - добавьте дополнительные геозоны при необходимости
4. Настройте uLogger:
   - endpoint: `http://YOUR_OSYS_HOME/GpsTracker/client/index.php`
   - user (строка): например `john`
5. Проверьте отправку (curl-логика):

```bash
curl -c cookies.txt -X POST "http://your-server/GpsTracker/client/index.php" \
  -d "action=auth&user=john"

curl -b cookies.txt -X POST "http://your-server/GpsTracker/client/index.php" \
  -d "action=addpos&lat=55.751244&lon=37.618423&time=1710000000&accuracy=30&provider=gps&comment=Yandex%20Address&battlevel=80&charging=false"
```

Результат:
- появятся точки в `GpsTracker -> Log`
- обновятся `<object>.latlon`, `<object>.home`, `<object>.location`, `<object>.address`, `<object>.battery`, `<object>.isCharging`

## Сценарий 2 (для новичка): OwnTracks для “нескольких людей”
1. Для каждого человека создайте объект и свойства как в сценарии 1.
2. В `GpsTracker -> Devices` привяжите каждый `Device` к соответствующему объекту (`Linked object`).
3. Настройте OwnTracks на отправку на:
   - `http://YOUR_OSYS_HOME/GpsTracker/owntracks?apikey=YOURKEY`
4. OwnTracks будет присылать JSON location.

Пример тела location (как в разделе `protocols-owntracks.ru.md`):
```json
{
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
}
```

Результат:
- ваша БД пополняется `GpsPosition`
- свойства объектов обновляются так же, как и для uLogger
- дополнительно OwnTracks может получить “друзей” (location/card) — если у других `GpsDevice` задан `linked_object`

## Сценарий 3 (для опытных): ручная отправка через REST API
Если вы не хотите поднимать uLogger/OwnTracks и просто хотите протестировать модель данных, можно отправить позицию напрямую.

Пример:
```bash
curl -X POST "http://your-server/api/GpsTracker/position?apikey=YOURKEY" \
  -H "Content-Type: application/json" \
  -d '{
    "device": "john_ulogger",
    "lat": 55.751244,
    "lon": 37.618423,
    "accuracy": 30,
    "speed": 0.1,
    "battery": 82,
    "charging": false,
    "provider": "manual",
    "address": "Test",
    "added": "2026-03-20T12:34:56"
  }'
```

Примечание:
- REST-ручка удобна для интеграций и отладки
- для обновления свойств в osysHome всё равно нужна корректная привязка `linked_object` и заранее созданные свойства объекта

## Что можно дальше сделать
- Использовать `home`/`location`/`isCharging` в задачах cron (например, включать автоматизацию “когда дома”).
- Использовать `home_distance`, чтобы реагировать на приближение (например, “если ближе 500м”).

