# GpsTracker - Модуль GPS отслеживания

![GpsTracker Icon](static/GpsTracker.png)

GPS-трекинг для osysHome: приём координат с телефонов/трекеров, геозоны, история и карта.

## Возможности

- Приём координат через **uLogger**, **OwnTracks** и REST
- Устройства (`GpsDevice`), геозоны (`GpsLocation`), история (`GpsPosition`)
- Определение «дома» / геозон и обновление linked-объектов
- Карта в админке: треки, правка геозон, перемещение/удаление точек трека
- Статистика истории и инструменты очистки
- Reverse geocoding (опционально)
- MCP (см. `docs/mcp.ru.md`)

## Панель администратора

Вкладки: Devices, Location, Log, History, Map, Settings.

Редактирование геозон и точек трека — только на вкладке **Map**. Полноэкранная `/page/GpsTracker` — только просмотр.

Подробнее: `docs/map-ui.ru.md`.

## Протоколы и API

- uLogger: `/GpsTracker/client/index.php`
- OwnTracks: `POST /api/GpsTracker/owntracks?apikey=...`
- REST: `docs/rest-api.ru.md`

## Определение адреса

- `docs/address-geocoding.ru.md`
- `docs/address-geocoding.md`

## Документация

- `docs/index.ru.md`

## Версия

**0.7**

## Категория

App

## Автор

Eraser
