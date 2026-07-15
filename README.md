# Tabigat-viz

Просмотрщик и выгрузка реестров платформы **Tabigat / KGS** (`https://tabigat.gov.kz`).

Все list-эндпоинты API построены на `@nestjsx/crud` (единые параметры `filter / sort / page / limit`
и формат ответа `{data, total, page, pageCount}`), поэтому один универсальный просмотрщик работает
со всеми ~108 реестрами: фильтрация, сортировка, пагинация и экспорт в CSV/Excel.

## Установка

```bash
cd /Users/taishaliya/platforms/tabigat/source/tabigat-viz
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Обновление каталога реестров

Спецификация OpenAPI встроена в `swagger-ui-init.js` — скрипт скачивает её и строит каталог:

```bash
python scripts/fetch_openapi.py
# -> data/openapi.json, data/registries.json (≈108 реестров)
```

## Запуск

```bash
streamlit run app.py
```

1. Введите логин/пароль платформы (хранятся только в памяти текущей сессии).
2. Выберите домен и реестр в левой панели.
3. Задайте фильтр/сортировку/пагинацию и нажмите «Загрузить».
4. Выгрузите выборку в CSV или Excel.

## Структура

| Путь | Назначение |
|------|-----------|
| `app.py` | точка входа: гейт авторизации, выбор реестра |
| `tabigat/api.py` | HTTP-клиент: логин, refresh, get_many, entity_meta |
| `tabigat/auth.py` | форма логина и хранение клиента в session_state |
| `tabigat/crud_query.py` | сборка crud-параметров запроса |
| `tabigat/registries.py` | каталог реестров из `data/registries.json` |
| `tabigat/tables.py` | таблица + фильтры + пагинация + экспорт |
| `scripts/fetch_openapi.py` | скачивание спецификации и построение каталога |

## Дальше

Под конкретные данные/реестр можно добавить отдельную преднастроенную страницу
(в каталоге `pages/`) поверх универсального просмотрщика — с нужными колонками,
фильтрами по умолчанию и при необходимости графиками.
