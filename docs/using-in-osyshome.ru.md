# Привязка к osysHome: `linked_object` и свойства

Внутри `GpsTracker` нет “настоящих GPS-объектов osysHome”. Модуль хранит треки в своей БД (`GpsDevice`, `GpsLocation`, `GpsPosition`), а в osysHome обновляет **свойства обычных объектов** через привязку `Linked object`.

## Что такое `linked_object`
В админке GpsTracker (вкладка **Devices**) у каждого устройства есть поле **Linked object** — имя объекта osysHome.

Когда модуль получает новые координаты для устройства, он:
1. вычисляет “дом” и геозоны
2. обновляет свойства объекта osysHome из `Linked object`

## Какие свойства обновляются
При наличии `linked_object` модуль обновляет следующие свойства объекта:

- `<object>.latlon` — строка формата `"<lat>,<lon>"`
- `<object>.location` — название геозоны (из `GpsLocation.title`) или `null`
- `<object>.home` — `1` (в радиусе дома) или `0` (вне радиуса). Если тип свойства в osysHome — `bool`, то будет `True/False`.
- `<object>.address` — название геозоны или значение `comment` из uLogger (если геозона не подошла)
- `<object>.home_distance` — расстояние до “дома” в метрах (float) или `null`
- `<object>.battery` — уровень батареи (число, источник зависит от протокола) или `null`
- `<object>.isCharging` — `true/false` (в OwnTracks считается по `bs`, в uLogger — по `charging`)

Важно: модуль использует обновление через `updatePropertyThread(...)`, поэтому **свойства должны существовать заранее** в объекте osysHome. Если их не создать, обновления не запишутся.

## Как подготовить объект (минимальный набор)
1. Откройте `Admin -> Objects` и создайте объект, например: `JohnPhone`.
2. Добавьте свойства с точными именами:
   - `latlon` (тип `str`)
   - `location` (тип `str`)
   - `home` (удобнее тип `bool`)
   - `address` (тип `str`)
   - `home_distance` (тип `float`)
   - `battery` (тип `float` или `int`)
   - `isCharging` (тип `bool`)
3. В `Admin -> GpsTracker -> Devices` создайте устройство и укажите `Linked object = JohnPhone`.

## Как это использовать в автоматизациях (для новичка)
В методах/тасках osysHome можно читать значения свойств через `getProperty(...)`.

Пример:
```python
# Пример: реакция на состояние "дома"
home = getProperty("JohnPhone.home")
if home:
    # Здесь ваши действия (например, включить свет)
    pass
```

## Что дополнительно можно узнать опытным пользователям
- `home`/`home_distance` вычисляются только если в GpsTracker существует геозона с `Is home = true`.
- `location` берётся по первой геозоне, в которую попала точка (порядок не фиксируется `ORDER BY`).

