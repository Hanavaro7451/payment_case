# Квитто: API платежей

Небольшой сервис на FastAPI, SQLAlchemy и PostgreSQL. HTTP-маршруты находятся в
`app/api.py`, схемы запросов и ответов — в `app/schemas.py`, правила платежей —
в `app/services.py`, доступ к данным — в `app/repositories.py`. Структуру БД
создают миграции Alembic. Суммы и скидки хранятся в целых копейках.

## Быстрый запуск

Нужен Docker с плагином Compose. Из корня проекта:

```sh
docker compose up --build
```

После готовности PostgreSQL контейнер API выполняет `alembic upgrade head`,
затем запускает Uvicorn. API доступен на <http://localhost:8000>, интерактивная
документация — на <http://localhost:8000/docs>. При старте создаются тарифы
`basic`, `standard`, `premium`, если их ещё нет. Данные PostgreSQL сохраняются
в Docker volume. Остановить сервисы: `docker compose down`.

Compose использует демонстрационные логин и пароль БД `kvitto` / `kvitto` и
демонстрационный секрет вебхука `local-demo-secret`. Эти значения подходят
только для локальной проверки. Чтобы задать свой секрет, скопируйте
`.env.example` в `.env` и измените `WEBHOOK_SECRET`. Файл `.env` не добавляется
в Git. Для других сред задавайте секреты извне и используйте отдельную
конфигурацию базы данных.

## Примеры запросов

Команды ниже рассчитаны на PowerShell. В `curl.exe` использован явный суффикс,
чтобы не вызвать одноимённый псевдоним PowerShell.

```powershell
curl.exe http://localhost:8000/tariffs

curl.exe -X POST http://localhost:8000/payments `
  -H "Content-Type: application/json" `
  -H "Idempotency-Key: example-checkout-1" `
  --data-raw '{"tariff_id":"standard","email":"student@example.com","method":"card","promo_code":"KVITTO10"}'

curl.exe "http://localhost:8000/payments?email=student@example.com&status=pending"
```

Для вебхука возьмите `id` созданного платежа вместо `1`. Подпись — HMAC-SHA256
от **точных байтов** JSON в теле запроса; любое изменение пробелов после
вычисления подписи сделает её неверной.

```powershell
$body = '{"payment_id":1,"status":"succeeded"}'
$signature = python -c "import hashlib,hmac,sys; print(hmac.new(b'local-demo-secret', sys.argv[1].encode(), hashlib.sha256).hexdigest())" $body
curl.exe -X POST http://localhost:8000/webhooks/bank `
  -H "Content-Type: application/json" `
  -H "X-Signature: $signature" `
  --data-raw $body
```

Допустимые переходы: `pending → succeeded`, `pending → failed`,
`succeeded → refunded`. Повторный или недопустимый переход возвращает `409`.
Повторный `POST /payments` с тем же `Idempotency-Key` возвращает исходный
платёж и `200` вместо нового платежа.

## Локальная разработка и проверки

Нужны Python 3.11+ и PostgreSQL. Приложение и Alembic читают `DATABASE_URL`;
значение по умолчанию —
`postgresql+psycopg://kvitto:kvitto@localhost:5432/kvitto`. Перед прямым
запуском создайте такую БД либо задайте собственный URL. Для вебхука также
задайте `WEBHOOK_SECRET`.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:DATABASE_URL = "postgresql+psycopg://kvitto:kvitto@localhost:5432/kvitto"
$env:WEBHOOK_SECRET = "local-demo-secret"
alembic upgrade head
uvicorn app.main:app --reload
```

Для запуска проверок:

```powershell
ruff check .
pytest -q
alembic check
```

Тесты API используют отдельную временную SQLite-базу; CI дополнительно
применяет миграции и проверяет соответствие моделей схеме на PostgreSQL.
Workflow запускается на каждый push и pull request. История использования ИИ
и проверки результата описана в [AI_LOG.md](AI_LOG.md).
