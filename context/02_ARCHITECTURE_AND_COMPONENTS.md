# 02. Архитектура и компоненты системы

## 📁 Структура кодовой базы

```
Kiwi-SPI/
├── .github/                # CI/CD workflows, Dependabot, issue templates
├── .circleci/              # CircleCI конфигурация
├── docs/                   # Официальная документация проекта (Sphinx / ReadTheDocs)
├── etc/                    # Конфигурационные файлы Nginx, uWSGI, cron jobs
├── helm/                   # Helm-чарты для деплоя в Kubernetes
├── kiwi_lint/              # Кастомные плагины для Pylint (проверки чистоты кода и безопасности)
├── requirements/           # Файлы зависимостей pip (base, devel, postgres, mariadb, readthedocs)
├── tcms/                   # Основной исходный код приложения Django
│   ├── bugs/               # Модуль встроенного баг-трекера
│   ├── core/               # Ядро: базовые модели, мидлвары, контекст-процессоры, шаблоны
│   ├── issuetracker/       # Адаптеры интеграции с внешними баг-трекерами (Jira, GitHub, etc.)
│   ├── kiwi_attachments/   # Модуль работы с вложениями
│   ├── kiwi_auth/          # Авторизация, регистрация, кастомные бекенды и формы
│   ├── locale/             # Файлы локализации (i18n / gettext)
│   ├── management/         # Управление продуктами, версиями, тегами и Django management commands
│   ├── rpc/                # JSON-RPC 2.0 и XML-RPC API интерфейс
│   ├── settings/           # Настройки Django (common, devel, product, test)
│   ├── static/             # Статические ресурсы (JS, CSS, изображения, PatternFly)
│   ├── telemetry/          # Модуль метрик, графиков и аналитики
│   ├── templates/          # HTML-шаблоны страниц
│   ├── testcases/          # Управление тест-кейсами, категориями, шагами и свойствами
│   ├── testplans/          # Управление тест-планами и древовидными структурами
│   ├── testruns/           # Управление тестовыми запусками (Runs) и исполнениями (Executions)
│   ├── utils/              # Вспомогательные утилиты, парсеры Markdown, работа с секретами
│   ├── urls.py             # Главный URL-роутер проекта
│   ├── signals.py          # Обработчики сигналов Django
│   ├── wsgi.py             # Точка входа WSGI
│   └── xmlrpc_wrapper.py   # Обёртка обратной совместимости для XML-RPC
├── tcms_settings_dir/      # Пользовательская директория настроек для локальных переопределений
└── tests/                  # Интеграционные, нагрузочные (Locust), Docker и UI (Robot/Selenium) тесты
```

---

## 🧩 Подробный разбор модулей (`tcms.*`)

### 1. `tcms.core` (Ядро системы)
- **Модели**: `UrlMixin` (предоставляет методы генерации URL), `KiwiHistoricalRecords` (наследует `simple_history` с аудитом пользователей).
- **Middleware**:
  - `CheckDBStructureExistsMiddleware`: проверяет инициализацию структуры БД и при необходимости перенаправляет на `/init-db/`.
  - Стандартный стек Django (CSRF, Sessions, Locale, Clickjacking, History).
- **Контекст-процессоры**: `request_contents_processor`, `settings_processor`, `server_time_processor`.
- **Навигация**: `MENU_ITEMS` генерирует главное меню приложения с учетом включенных плагинов.

### 2. `tcms.testplans` (Тест-планы)
- **Модели**:
  - `TestPlan`: Наследует `tree_queries.models.TreeNode` для иерархии планов. Содержит ссылки на `Product`, `Version`, `PlanType`, автора, теги, настройки рассылок.
  - `PlanType`: Тип тест-плана (интеграционный, регрессионный, приемочный и т.д.).
  - `TestPlanTag`, `TestPlanEmailSettings`.
- **Функционал**: Клонирование планов (`make_cloned_name`), добавление/удаление тест-кейсов с автоматическим расчетом `sortkey`.

### 3. `tcms.testcases` (Тест-кейсы)
- **Модели**:
  - `TestCase`: Карточка тест-кейса со связями на категорию, статус (`TestCaseStatus`), приоритет, автора, ревьюера, дефолтного тестировщика.
  - `TestCaseStatus`: Статусы кейсов (`is_confirmed` флаг).
  - `Category`: Категории внутри продукта.
  - `Property`: Произвольные параметры тестов для построения комбинаторных матриц.
  - `TestCasePlan`: Связующая модель для упорядоченного включения кейсов в планы.
  - `BugSystem`: Конфигурация подключения к баг-трекерам (URL, API endpoints, авторизационные токены).

### 4. `tcms.testruns` (Тестовые прогоны и исполнения)
- **Модели**:
  - `TestRun`: Запуск плана под конкретный `Build`. Содержит плановые и фактические даты, ответственного менеджера, подписчиков (CC).
  - `TestExecution`: Запуск отдельного тест-кейса в рамках Run'а. Имеет статус (`TestExecutionStatus`: IDLE, PASSED, FAILED и др.), исполнителя (`tested_by`), продолжительность.
  - `TestExecutionProperty`: Назначенные свойства окружения для конкретного исполнения.
- **Матрица выполнений (`property_matrix`)**:
  - Генерация комбинаций свойств тест-кейсов и окружения.
  - Поддерживает два режима: `full` (полное декартово произведение) и `pairwise` (ортогональный массив / Pairwise-тестирование через `allpairspy`).

### 5. `tcms.bugs` & `tcms.issuetracker` (Интеграция с трекерами дефектов)
- **Архитектура адаптеров**: Базовый абстрактный класс `tcms.issuetracker.base.IssueTrackerType` определяет единый интерфейс:
  - `is_adding_testcase_to_issue_disabled()`
  - `details(url)` — получение метаданных бага по ссылке.
  - `post_process_new_issue(issue, execution)` — хуки пост-обработки.
  - `auto_link_bug()` — 1-click создание и привязка тикета в баг-трекере к `TestExecution`.
- **Реализованные трекеры (`tcms/issuetracker/`)**:
  - `jira.py` — Jira Server & Cloud (REST API).
  - `github.py` / `gitlab_*.py` — GitHub & GitLab (Issues API).
  - `bugzilla_integration.py` — Bugzilla (XML-RPC/REST).
  - `redmine.py` — Redmine API.
  - `azure_boards.py` — Azure DevOps Boards.
  - `kiwitcms.py` — Внешний инстанс Kiwi TCMS.

### 6. `tcms.rpc` (API Интерфейс)
- **Протоколы**: JSON-RPC 2.0 (`/json-rpc/`) и XML-RPC (`/xml-rpc/`), реализованные через `django-modern-rpc`.
- **Пространства имен API**:
  - `Auth.*` (login, logout, credentials)
  - `TestPlan.*`, `TestCase.*`, `TestRun.*`, `TestExecution.*`
  - `Product.*`, `Version.*`, `Build.*`, `Component.*`, `Category.*`, `Classification.*`, `Priority.*`, `Tag.*`
  - `Bug.*`, `BugTracker.*`, `Attachment.*`, `User.*`, `Group.*`, `Markdown.*`
- **Безопасность и валидация**:
  - Декораторы `@rpc_method`, `@permissions_required`.
  - Валидация входных аргументов через Django Forms (`tcms/rpc/api/forms/`).
  - Поддержка как позиционных аргументов, так и именованных параметров (Named Parameters).

### 7. `tcms.telemetry` (Аналитика и дашборды)
- **Представления**:
  - `TestingBreakdownView`: Распределение результатов тестирования.
  - `StatusMatrixView`: Матрица статусов по билдам, компонентам и средам.
  - `ExecutionTrendsView`: Временные тренды прохождения тестов.
  - `TestCaseHealthView`: Индекс стабильности тест-кейсов (flakiness, частые падения).

### 8. `tcms.kiwi_auth` (Аутентификация и пользователи)
- **Функции**:
  - Авторизация через Django Auth + Guardian Object Permissions.
  - Механизм подтверждения пользователей (`AUTO_APPROVE_NEW_USERS`).
  - Защита формы регистрации с помощью CAPTCHA.
  - Настраиваемые валидаторы корпоративных email (`EMAIL_VALIDATORS`).

---

## 🔌 Плагины и точки расширения

Kiwi TCMS использует стандартный механизм Python `entry_points` для автоматического обнаружения и подключения плагинов:

```python
# Автоматическая загрузка установленных плагинов в INSTALLED_APPS и роутер
for plugin in entry_points().select(group="kiwitcms.plugins"):
    INSTALLED_APPS.append(plugin.value)
    # URLs: tcms/urls.py
    plugin_urls = import_module(f"{plugin.value}.urls")
    urlpatterns.append(re_path(f"^{plugin.name}/", include(plugin_urls)))
```

---

## 🎨 Фронтенд-пайплайн

- Исходные ассеты находятся в `tcms/static/`.
- Сборщик: **Webpack 5** (`tcms/webpack.config.js`).
- UI-компоненты построены на базе дизайн-системы **PatternFly**.
- Сборка итогового бандла:
  ```bash
  cd tcms/
  npm install
  npx webpack --mode=production
  ```
- Локализация фронтенда использует Django `JavaScriptCatalog` (`/jsi18n/`).

---

## 🛡 Пользовательские проверки `kiwi_lint`

Директория `kiwi_lint/` содержит специализированные расширения для Pylint:
- Проверка запрета жестко закодированных строк и путей.
- Контроль корректности вызова методов миграций и валидации `OneToOneField`.
- Проверка структуры моделей и параметров вызовов RPC.
