# История сессии — создание проекта tabigat-viz

> Снимок разговора с Claude Code (Opus 4.8). Дата: 2026-06-04.
> Чтобы вернуться к контексту — прочитайте этот файл и [README.md](README.md).

---

## 1. Исходная задача (от пользователя)

> Напиши проект для визуализации нужных данных (какие именно — подскажу позже)
> со Swagger `https://tabigat.gov.kz/apidocs`.
> Для авторизации в Swagger нужен токен. Чтобы получить токен:
>
> ```bash
> curl -X 'POST' \
>   'https://tabigat.gov.kz/api/v1/auth/main/auth/login' \
>   -H 'accept: application/json' \
>   -H 'Content-Type: application/json' \
>   -d '{ "username": "<ввод вручную>", "password": "<ввод вручную>" }'
> ```

## 2. Что выяснили про API (этап исследования)

- **Платформа:** KGS Platform API («Tabigat»), OpenAPI 3.0, версия 0.0.1. Base URL `https://tabigat.gov.kz`.
- **Масштаб:** 1001 эндпоинт, 439 схем.
- **Спецификация** не отдаётся как `/openapi.json` (404) — она **встроена в `swagger-ui-init.js`**
  как объект `swaggerDoc` (~2.26 МБ). Достаём сопоставлением фигурных скобок.
- **Авторизация:** Bearer JWT (`securitySchemes: access-token`).
  - Логин: `POST /api/v1/auth/main/auth/login` тело `{username, password}` → `201`.
    Схема ответа в спеке — generic object, **точные имена полей токена не описаны**
    (определяем по факту: `accessToken` / `access_token` / `token`).
  - Обновление: `POST /api/v1/auth/main/auth/refresh-token`.
  - Также есть login-with-eds / login-qr / login-ispr / login-device.
- **Главное открытие:** все list-эндпоинты построены на **`@nestjsx/crud`**:
  - единые query-параметры: `filter, s, or, sort, join, fields, limit, offset, page, cache`;
  - единый ответ: `{ data: [], count, total, page, pageCount }` (либо просто массив);
  - у каждой сущности есть `GET {path}/entity-meta` (список колонок).
  - **Вывод:** один универсальный просмотрщик покрывает все реестры сразу.
- **Реестров («Retrieve multiple …»): 108.** По доменам:
  | домен | реестров | RU-название |
  |-------|---------:|-------------|
  | tab-forest | 44 | Лесное хозяйство |
  | users | 20 | Пользователи и оргструктура |
  | gis | 18 | ГИС / карты |
  | events | 8 | События и уведомления |
  | tab-animals | 6 | Животный мир |
  | docs | 4 | Документы |
  | processes | 4 | Процессы |
  | lists | 2 | Справочники |
  | fires | 1 | Пожары |
  | tasks | 1 | Задачи |
- Рядом в `source/` лежат `platform_tabigat` (backend) и `platform_tabigat_front` — репозиторий той же платформы.

## 3. Решения пользователя (через уточняющие вопросы)

| Вопрос | Ответ |
|--------|-------|
| Стек | **Python + Streamlit** |
| Тип визуализации | **Таблицы / реестры** (фильтры + экспорт). Карты/графики пока не нужны |
| Папка проекта | `/Users/taishaliya/platforms/tabigat/source/tabigat-viz` |

## 4. Что реализовано

Универсальный Streamlit-просмотрщик реестров. Структура:

```
tabigat-viz/
├── app.py                     # гейт логина + выбор домена/реестра
├── tabigat/
│   ├── config.py              # BASE_URL, лимиты, RU-названия доменов
│   ├── api.py                 # ApiClient: login / refresh / get_many / entity_meta / get_one
│   ├── auth.py                # форма логина, токен в st.session_state, авто-refresh, logout
│   ├── crud_query.py          # сборка crud-параметров (filter/sort/page/limit, операторы $cont/$eq/...)
│   ├── registries.py          # каталог реестров из data/registries.json по доменам
│   └── tables.py              # таблица + фильтр/сортировка/пагинация + экспорт CSV/Excel
├── scripts/fetch_openapi.py   # качает swagger-ui-init.js → data/openapi.json + registries.json
├── data/openapi.json          # спецификация (1001 путь), в .gitignore
├── data/registries.json       # каталог (108 реестров)
├── .streamlit/config.toml
├── requirements.txt           # streamlit, requests, pandas, openpyxl
├── README.md
└── SESSION.md                 # этот файл
```

**Ключевые детали реализации:**
- Токен ищется по списку вероятных ключей, в т.ч. во вложенных `data/tokens/result` (`api._find_token`).
- При `401` клиент один раз пытается refresh и повторяет запрос.
- Учётные данные вводятся только в форме и живут в `st.session_state` — на диск не пишутся.
- Вложенные dict/list в ячейках таблицы сворачиваются в компактный JSON.

## 5. Проверка (что прогнали)

- ✅ venv создан, зависимости установлены (streamlit 1.58.0, pandas 3.0.3).
- ✅ `python scripts/fetch_openapi.py` → 1001 путь, 108 реестров.
- ✅ Импорт всех модулей + smoke-тест хелперов (build_params, find_token, flatten df) — OK.
- ✅ `streamlit run app.py` стартует, HTTP 200 на `/` и `/_stcore/health`, без ошибок в логе.
- ⏳ Реальный логин не тестировался — логин/пароль вводит пользователь вручную в форме.

## 6. Как запустить

```bash
cd /Users/taishaliya/platforms/tabigat/source/tabigat-viz
source .venv/bin/activate
streamlit run app.py
# затем: ввести логин/пароль → выбрать домен и реестр → фильтр/сортировка → экспорт CSV/Excel
```

Обновить каталог реестров (если API изменился):
```bash
python scripts/fetch_openapi.py
```

## 7. Следующий шаг (открыто)

Пользователь назовёт **конкретные данные / реестр / поля** для целевой визуализации.
Тогда: добавить преднастроенную страницу в `pages/` поверх универсального просмотрщика —
нужные колонки, фильтры по умолчанию и при необходимости графики.
