# 03. Руководство по разработке и эксплуатации

## 🛠 Подготовка локального окружения

### Системные требования:
- **Python**: 3.12+
- **Node.js & npm**: Node.js 24+
- **СУБД**: MariaDB 10.5+ или PostgreSQL 15+ (для локальных тестов доступен SQLite)
- **Системные пакеты**: `gcc`, `gettext`, `libjpeg-turbo-devel`, `libffi-devel`, `postgresql-devel` / `mariadb-connector-c-devel`.

### Установка зависимостей Python:
```bash
# 1. Создание и активация виртуального окружения
python -m venv .venv
source .venv/bin/activate  # на Linux/macOS
# или .venv\Scripts\Activate.ps1 на Windows

# 2. Установка базовых и dev-зависимостей
pip install --upgrade pip setuptools wheel
pip install -r requirements/base.txt
pip install -r requirements/devel.txt
pip install -r requirements/postgres.txt   # если используется PostgreSQL
pip install -r requirements/mariadb.txt    # если используется MariaDB
```

### Сборка фронтенд-ассетов:
```bash
cd tcms/
npm install
./node_modules/.bin/webpack
cd ..
```

---

## 🚀 Запуск проекта

### 1. Локальный запуск (Django Dev Server)
По умолчанию в `manage.py` прописаны настройки `tcms.settings.devel` (используется SQLite):

```bash
# Компиляция переводов
python manage.py compilemessages

# Применение миграций
python manage.py migrate

# Создание суперпользователя и начальных данных
python manage.py initial_setup

# Запуск сервера
python manage.py runserver 0.0.0.0:8000
```

### 2. Запуск через Docker Compose (Рекомендуемый для продакшна/стендов)

**С базой MariaDB (по умолчанию):**
```bash
docker compose up -d
```
Сервер будет доступен на портах:
- `http://localhost:80` (редирект на 443)
- `https://localhost:443` (самоподписанный SSL сертификат)

**С базой PostgreSQL:**
```bash
docker compose -f docker-compose.postgres up -d
```

---

## 🗄 Работа с базой данных и миграции

### Создание и проверка миграций:
```bash
# Проверка отсутствующих миграций
python manage.py makemigrations --check --settings=tcms.settings.test

# Создание новых миграций после изменения моделей
python manage.py makemigrations

# Применение миграций к конкретной БД
python manage.py migrate --database=default
```

### Служебные команды инициализации:
- `python manage.py initial_setup` — создает базовые группы, права, стандартные статусы (`TestCaseStatus`, `TestExecutionStatus`), дефолтные приоритеты и администратора.
- `python manage.py set_domain <domain>` — настраивает домен сайта в `django.contrib.sites`.

---

## 🧪 Тестирование

### 1. Запуск Unit & Integration тестов Django:
```bash
# Запуск с дефолтными тестовыми настройками (SQLite)
python manage.py test -v2 --settings=tcms.settings.test

# Запуск тестов для конкретного приложения
python manage.py test tcms.testcases --settings=tcms.settings.test
python manage.py test tcms.rpc --settings=tcms.settings.test

# Запуск с замером покрытия
coverage run --source='.' manage.py test -v2 --settings=tcms.settings.test
coverage report -m
```

### 2. Запуск тестов под конкретными СУБД (через Makefile):
```bash
TEST_DB=Postgres make test
TEST_DB=MariaDB make test
TEST_DB=all make test
```

### 3. Проверка сборки Docker и E2E тесты:
```bash
make docker-image
./tests/runner.sh
```

### 4. Нагрузочное тестирование (Locust):
```bash
locust -f tests/performance/locustfile.py --headless -u 50 -r 10 --run-time 1m --host http://localhost:8000
```

---

## 🔍 Статический анализ и контроль качества кода

В проекте настроен жесткий пайплайн статического анализа:

| Команда | Инструмент | Назначение |
| :--- | :--- | :--- |
| `make flake8` | `flake8` | Проверка PEP8 и базового синтаксиса |
| `make pylint` | `pylint` + `pylint_django` + `kiwi_lint` | Глубокий анализ кода, моделей, миграций и антипаттернов |
| `make bandit` | `bandit` | Анализ уязвимостей безопасности в Python коде |
| `make similar_strings` | `kiwi_lint` | Поиск дублирующихся строковых литералов |
| `make doc8` | `doc8` | Валидация форматирования документации Sphinx/reST |
| `make check` | Composite | Выполняет `flake8` и полный прогон тестов |

---

## 🌐 Локализация (i18n)

```bash
# Генерация новых .po файлов сообщений
make messages

# Компиляция переводов в .mo бинарники
python manage.py compilemessages
```
Переводы синхронизируются через платформу Crowdin.
