# Family Budget (Python)

Клон сервиса учёта семейных расходов: FastAPI + PostgreSQL + Alembic, Telegram-бот с
ИИ-агентом и веб-панель для главы семьи.

Член семьи пишет боту «кофе 350» — бот сам определяет сумму, категорию и дату и
сохраняет трату. Глава семьи входит в веб-панель, видит и редактирует траты всех
членов семьи.

## Стек

| Слой | Технология |
| --- | --- |
| Язык | Python 3.12 |
| Web | FastAPI + Uvicorn |
| БД | PostgreSQL 16, SQLAlchemy 2.0 async + asyncpg |
| Миграции | Alembic |
| Авторизация | Argon2id + JWT (access) + opaque refresh-токены в HttpOnly cookie |
| Telegram | aiogram 3 (long polling или webhook) |
| LLM | OpenAI-совместимый API (OpenRouter), tool calling |
| Фронтенд | Vue 3 + TypeScript + Vite + Tailwind CSS 4 |
| Запуск | docker compose + Makefile |

## Быстрый старт

```bash
cp .env.example .env
# заполните JWT_SECRET, LLM_API_KEY и TELEGRAM_BOT_TOKEN
make up
```

- Панель: http://localhost:5173
- API: http://localhost:8080
- Swagger: http://localhost:8080/docs

Миграции применяет one-shot контейнер `migrate` (`alembic upgrade head`) до старта
backend. Демо-данные:

```bash
make seed-docker
```

Сид печатает учётные данные главы, инвайт-код и одноразовую ссылку для входа в панель:

```
head: head@example.com / password123
invite code: DEMO2026
panel: http://localhost:5173/login?code=...
```

Остановить: `make down`.

## Авторизация

В отличие от оригинала, панель защищена. Доступ к дашборду есть **только у главы
семьи**; остальные участники работают через Telegram-бота.

### Первый вход

1. Глава отправляет боту `/panel`.
2. Бот создаёт одноразовый код (TTL 5 минут, в БД хранится только SHA-256) и присылает
   ссылку `PANEL_URL/login?code=...`.
3. Панель меняет код на access-токен и refresh-cookie.
4. Если пароль ещё не задан, панель просит email и пароль. Дальше можно входить через
   вкладку «Email и пароль».

### Токены

- **Access**: JWT HS256, 15 минут, передаётся в `Authorization: Bearer` и хранится
  только в памяти фронтенда.
- **Refresh**: случайный opaque-токен, 30 дней, HttpOnly + SameSite=Lax cookie с путём
  `/api/auth`; в БД хранится SHA-256, при обновлении выполняется ротация. Повторное
  использование отозванного токена инвалидирует все сессии пользователя.
- Пароли — Argon2id, минимум 8 символов.
- На `/api/auth/login` и `/api/auth/code-login` действует ограничение попыток.
- CORS разрешён только для origins из `CORS_ORIGINS`.

### Роли

`family_members.role`:

- `head` — создаёт семью, приглашает участников, имеет доступ к панели и видит траты
  всей семьи;
- `member` — вступает по инвайт-коду через бота, видит и редактирует только свои траты
  в боте; панель для него возвращает `403`.

## Telegram-бот

- `/start` — регистрирует пользователя и создаёт семью (глава).
- `/start <код>` — вступает в семью по ссылке-приглашению.
- `/invite` — ссылка `https://t.me/<bot>?start=<invite_code>`.
- `/panel` — одноразовая ссылка в веб-панель (только главе).
- Любой другой текст уходит ИИ-агенту: «кофе 350», «такси 1200 вчера», «сколько
  потратил на еду за месяц», «удали такси».

Агент работает по схеме tool calling с функциями `add_expense`, `list_expenses`,
`get_total`, `update_expense`, `delete_expense`. Идентификатор пользователя всегда
берётся из Telegram-апдейта, а не из аргументов модели, поэтому чужие траты недоступны.

Режим выбирается автоматически:

- задан только `TELEGRAM_BOT_TOKEN` — long polling (публичный URL не нужен);
- задан ещё `TELEGRAM_WEBHOOK_URL` — webhook на `POST /telegram/webhook` с проверкой
  `X-Telegram-Bot-Api-Secret-Token`.

Если `TELEGRAM_BOT_TOKEN` пуст, бот не запускается, API и панель работают.

## REST API

Все эндпоинты кроме `/api/health` и `/api/auth/*` требуют access-токен главы.

```
POST   /api/auth/code-login        # обмен кода из бота на токены
POST   /api/auth/login             # email + пароль
POST   /api/auth/refresh           # ротация refresh-cookie
POST   /api/auth/logout            # отзыв refresh-токена
GET    /api/auth/me                # текущий глава и семья
POST   /api/auth/password          # установка/смена email и пароля

GET    /api/family                 # семья + участники
GET    /api/family/members         # участники
POST   /api/family/invite/rotate   # перевыпуск инвайт-кода
GET    /api/users                  # алиас /api/family/members

GET    /api/expenses?user_id=&from=&to=&category=&limit=&offset=
POST   /api/expenses               # user_id необязателен, по умолчанию — сам глава
GET    /api/expenses/{id}
PATCH  /api/expenses/{id}
DELETE /api/expenses/{id}

GET    /api/health
POST   /telegram/webhook
```

Даты — `YYYY-MM-DD`. Категории: `еда, транспорт, жильё, развлечения, здоровье,
покупки, другое`. Ошибки возвращаются как `{"error": "..."}`.

## Структура

```
app/
  main.py                 # FastAPI app, lifespan, обработчики ошибок
  core/                   # config, security, deps, errors, rate limit
  db/                     # engine и async-сессии
  models/                 # users, families, family_members, expenses, tokens
  schemas/                # Pydantic-схемы
  api/routes/             # auth, family, expenses, health, telegram
  services/               # auth, families, expenses, agent, llm, bot
  bot/                    # aiogram handlers и runtime
  seed.py                 # демо-данные
alembic/                  # env.py и версии миграций
frontend/                 # Vue 3: login, setup-password, dashboard
tests/                    # pytest + httpx
docker/                   # образы backend и frontend
```

## Конфигурация

Все параметры — через переменные окружения (см. `.env.example`):

| Переменная | Назначение |
| --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://...` (в compose — хост `postgres`) |
| `JWT_SECRET` | секрет подписи JWT, обязательно длинный случайный |
| `ACCESS_TOKEN_TTL_MINUTES` | время жизни access-токена, по умолчанию 15 |
| `REFRESH_TOKEN_TTL_DAYS` | время жизни refresh-токена, по умолчанию 30 |
| `LOGIN_CODE_TTL_SECONDS` | TTL одноразового кода из бота, по умолчанию 300 |
| `PANEL_URL` | публичный адрес панели для ссылок из бота |
| `CORS_ORIGINS` | разрешённые origins через запятую |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | доступ к OpenAI-совместимому API |
| `TELEGRAM_*` | токен бота и настройки webhook |

`DATABASE_URL` можно указывать в формате `postgres://` или `postgresql://` — драйвер
`asyncpg` подставляется автоматически.

## Локальная разработка

```bash
uv sync
cp .env.example .env   # для локального запуска замените хост postgres на localhost
make migrate-up
make run               # uvicorn на :8080
make web-dev           # Vite на :5173, проксирует /api на :8080
```

Если локальный PostgreSQL занимает порт 5432, задайте `POSTGRES_PORT` в `.env` — Makefile
и compose используют его для публикации порта.

## Команды

| Команда | Действие |
| --- | --- |
| `make up` / `make down` | поднять / остановить compose |
| `make logs` | логи backend |
| `make migrate-up` / `migrate-down` / `migrate-status` | Alembic локально |
| `make revision m="..."` | новая автогенерируемая миграция |
| `make seed` / `make seed-reset` / `make seed-docker` | демо-данные |
| `make test` | pytest против `family_test` |
| `make test-db` | создать тестовую БД в compose-контейнере |
| `make lint` | ruff |

## Тесты

```bash
make test-db
make test
```

Покрыто: одноразовость и срок кода, вход по паролю, ротация и отзыв refresh-токенов,
запрет доступа участникам, CRUD трат в границах семьи, фильтры, scoping инструментов
ИИ-агента, вход в семью через бота.

## Troubleshooting

**`failed to fetch anonymous token ... TLS handshake timeout` при `make up`** — Docker не
смог достучаться до Docker Hub. Это сетевая проблема, не ошибка проекта. Проверьте
прокси/DNS, выполните `docker pull python:3.12-slim` и `docker pull node:22-alpine`,
затем повторите `make up`. Если используется прокси, его нужно прописать в настройках
Docker daemon, а не только в `HTTP_PROXY` shell.
