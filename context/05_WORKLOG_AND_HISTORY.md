# 05. Журнал изменений и история развития

## 📜 Хронология развития проекта (от Nitrate к Kiwi TCMS v16.4)

- **Февраль 2009**: Запуск проекта компанией Red Hat под названием **Nitrate**.
- **Ноябрь 2014**: Исходный код Nitrate опубликован на GitHub без предыдущей истории коммитов.
- **Май 2017**: Форк и перезапуск проекта под названием **Kiwi TCMS**. Удалена жесткая привязка к Red Hat Bugzilla, добавлена расширяемая архитектура внешних трекеров.
- **Сентябрь 2017**: Переход на современный UI на базе PatternFly, поддержка Python 3.5+, переход на Django 1.11+.
- **2018–2020**: Внедрение Pylint/Kiwi Lint, интеграции с GitLab/GitHub/Jira, публикация в GitHub Marketplace, победа в OpenAwards и Mozilla Open Source Seed Award.
- **2021–2023**: Преодоление отметки в 2 миллиона скачиваний Docker Hub. Внедрение объектного разграничения доступа, Pairwise-генерации матриц тестирования, Helm-чартов.
- **Август–Сентябрь 2026**:
  - Выпуск версии **16.3**: переход на Node.js 24, Django 6.0.8, обновление Helm-чартов, улучшение кэширования Markdown API.
  - Выпуск версии **16.4**: миграция на Django 6.1.1, закрытие уязвимостей безопасности в BugSystem и JSON-RPC, строгая типизация `URLField` для трекеров, обновление `psycopg` до 3.3.5.

---

## 📝 Журнал недавних коммитов (v16.4)

| Хеш | Автор | Описание изменения |
| :--- | :--- | :--- |
| `e280076da` | Alexander Todorov | Changelog for v16.4 |
| `42f93c31b` | dependabot | Bump django-guardian from 3.4.0 to 3.4.1 |
| `930a43ec7` | dependabot | Bump webpack from 5.110.2 to 5.110.3 in /tcms |
| `073711a4d` | dependabot | Bump django from 6.1 to 6.1.1 |
| `a6b102b4a` | Alexander Todorov | Replace BugSystemForm with existing BugSystemAdminForm |
| `e0ed92942` | Alexander Todorov | Validate BugSystem.tracker_type field against settings.EXTERNAL_BUG_TRACKERS |
| `e0f17cf3b` | Alexander Todorov | Add tests for BugSystem with invalid tracker_type values |
| `4ceceadd6` | Alexander Todorov | Add more JSON-RPC test for calls with named parameters |
| `6f7222bdb` | Alexander Todorov | Refactor BugSystem.base_url and BugSystem.api_url to URLField |
| `9156c9a91` | Alexander Todorov | Add JSON-RPC test with named parameters for User.filter |
| `7ca19c819` | Alexander Todorov | Overwrite all fields when saving BugSystem via Admin |
| `7fdcf8e31` | Alexander Todorov | Add test for saving BugSystem record via Admin change view |
| `9e0e9a774` | Alexander Todorov | Fix test_should_be_allowed_to_create_new_group for Django 6.1 |
| `c67c15613` | Alexander Todorov | Propagate the --database option to commands which support it |
| `cecd2a5ff` | Alexander Todorov | Add --database option to initial_setup & set_domain commands |

---

## 🛠 Журнал выполненных локальных работ

### [2026-09-09]
- Проведен комплексный аудит кодовой базы, зависимостей, настроек и архитектуры Kiwi-SPI.
- Создана выделенная база знаний контекста проекта (`context/`) со структурой:
  - `README.md` — индекс и правила ведения контекста.
  - `01_PROJECT_OVERVIEW.md` — концептуальный обзор и доменная модель.
  - `02_ARCHITECTURE_AND_COMPONENTS.md` — декомпозиция приложений и API.
  - `03_DEVELOPMENT_AND_OPERATIONS.md` — гайд по разработке, тестам и CI/CD.
  - `04_CURRENT_STATE.md` — текущий снимок версий и уязвимостей.
  - `05_WORKLOG_AND_HISTORY.md` — журнал истории и коммитов.
  - `06_ROADMAP_AND_PLANS.md` — планируемые задачи и точки расширения.

### [2026-10-07]
- Реализован интерфейс единого списка подразделов и тест-кейсов в стиле TestRail:
  - Доработан RPC-метод `TestPlan.tree`: добавлен параметр `subtree_only` и сбор списка привязанных тест-кейсов с `sortkey` для каждого плана в иерархии.
  - Добавлены Unit-тесты для `TestPlan.tree` в `tcms/rpc/tests/test_testplan.py`.
  - В `tcms/testplans/templates/testplans/get.html` добавлен шаблон секции `test_plan_section` и CSS-стили (аккордеоны, индикаторы вложенности, подсветка перехода).
  - В `tcms/testplans/static/testplans/js/get.js` переработано отображение тест-кейсов:
    - Сворачиваемые секции (Accordion) для родительского плана и каждого подраздела со счетчиками кейсов.
    - Быстрый навигатор в правом сайдбаре: клик по подразделу плавно скроллит к соответствующей секции и подсвечивает ее.
    - Кнопки добавления кейсов (новых и существующих) прямо внутри каждого подраздела.
    - Массовые операции, чекбоксы (на уровне секции и общий тулбар), удаление и фильтрация адаптированы под многосекционную модель.
  - Пересобран бандл Webpack (`bundle.js`), линтинг ESLint и тесты Django пройдены успешно.
- Реализован интерфейс единого списка подразделов и тест-исполнений (Test Executions) в стиле TestRail для запущенных тест-ранов (`TestRun`):
  - Создана ветка `feature/testrail-style-testruns-ui`.
  - В `tcms/testruns/templates/testruns/get.html`:
    - Добавлен шаблон секции `#test_run_section` с аккордеоном, чекбоксом секции, ссылкой на родительский/дочерний тест-план, мини-прогрессбаром статусов, счетчиком исполнений и кнопкой «+ Add case».
    - Интегрировано дерево планов `{{ object.plan.tree_view_html|safe }}` в карточку тест-рана.
    - Добавлены стили PatternFly/TestRail с отступами уровней вложенности (`.testrun-section-depth-0..4`), анимацией подсветки перехода (`.section-highlight`) и мини-прогрессбарами.
  - В `tcms/testruns/static/testruns/js/get.js`:
    - Загрузка дерева подразделов через `TestPlan.tree(planId, subtree_only=True)` и группировка тест-исполнений по соответствующим подразделам.
    - Сворачиваемые секции (Accordion) с динамическим мини-прогрессбаром (зеленый / серый / красный) и бейджами количества исполнений.
    - Быстрый навигатор по клику в дереве планов: плавный скролл к секции, автораскрытие и подсветка.
    - Чекбоксы секций и тулбара с поддержкой мульти-секционных массовых действий (статусы, исполнители, комментарии, удаление).
    - Автоматический переход к следующему тест-исполнению (включая переход в следующую секцию) при выставлении статуса тестирования.
    - Кнопка «+ Add case» в каждой секции с быстрым поиском тест-кейсов именно из этого подраздела.
    - Фильтрация с адаптивным скрытием пустых секций и пересчетом бейджей видимых записей.
  - Пройден линтинг ESLint (0 ошибок) и полный набор тестов `tcms.testruns` (47 тестов успешно).
  - Бандл Webpack скомпилирован и синхронизирован с рабочим контейнером `kiwi-local-web-1`.
- Реализовано иерархическое скрытие субкатегорий (подразделов) при сворачивании родительских категорий в Test Plans и Test Runs:
  - Создана ветка `feature/hierarchical-subsections-collapse`.
  - В `tcms/testplans/static/testplans/js/get.js` и `tcms/testruns/static/testruns/js/get.js`:
    - Добавлен атрибут `data-parent-id` для каждой секции плана/рана.
    - Реализована функция `updateSubsectionsVisibility()`, проверяющая цепочку предков для каждого подраздела: подраздел отображается только если все его предки раскрыты.
    - Реализована функция `expandSectionAndAncestors(planId)`: при клике в дереве быстрого перехода раскрываются все предки целевого подраздела, гарантируя его видимость и корректный скролл.
    - Синхронизировано состояние чекбоксов (`:visible`) и поведение при сбросе поискового фильтра.
  - Бандл Webpack пересобран (`npx webpack`), синхронизирован с Docker-контейнером `kiwi-local-web-1`, линтинг ESLint успешно пройден (0 ошибок).

### [2026-10-09]
- Удалена кнопка добавления тест-кейса («+ Add case») из полоски заголовка категорий/секций в тест-ранах (`TestRun`):
  - Создана ветка `feature/remove-add-case-from-testrun-sections`.
  - В `tcms/testruns/templates/testruns/get.html`:
    - Из шаблона `#test_run_section` удален блок `.testrun-section-actions` с кнопкой `.js-section-add-cases`.
    - Удалены неиспользуемые CSS-стили `.testrun-section-actions`.
  - В `tcms/testruns/static/testruns/js/get.js`:
    - Удален обработчик клика по `.js-section-add-cases` и неиспользуемые переменные `productId` и `testRunId` в функции `renderTestExecutions()`.
  - Бандл Webpack пересобран (`npx webpack`), синхронизирован с рабочим Docker-контейнером `kiwi-local-web-1`.
  - Линтинг ESLint пройден без замечаний (0 ошибок).
  - Набор тестов `tcms.testruns` пройден успешно (47 тестов).
- Исправлена ошибка 404 при добавлении нового тест-кейса через кнопку в заголовке секции тест-плана (`TestPlan`):
  - Создана ветка `feature/fix-section-new-case-404`.
  - В `tcms/testplans/templates/testplans/get.html` добавлен data-атрибут `data-new-testcase-url="{% url 'testcases-new' %}"`.
  - В `tcms/testplans/static/testplans/js/get.js` исправлен путь создания нового кейса с некорректного `/case/new/` на `/cases/new/?from_plan=${section.id}` (с использованием динамического `data-new-testcase-url`).
  - Бандл Webpack пересобран (`npx webpack`), синхронизирован с рабочим контейнером `kiwi-local-web-1`.
  - Линтинг ESLint пройден без замечаний (0 ошибок).
  - Наборы тестов `tcms.testplans` (37 тестов) и `tcms.testcases` (57 тестов) выполнены успешно.

### [2026-10-12]
- Устранена ошибка Forbidden при открытии тест-плана по клику на название категории/секции в интерфейсе тест-плана (`TestPlan`):
  - Создана ветка `feature/fix-category-plan-link-forbidden`.
  - Заголовок категории/секции (`.testplan-section-title`) сделан некликабельным: удален тег ссылки `<a>`, заголовок отображается простым текстом `<span>` со стандартным цветом `#151515` без стилей перехода по ссылке.
  - В `tcms/testplans/templates/testplans/get.html` шаблон `#test_plan_section` обновлен: `<a>` заменен на `<span class="testplan-section-title js-section-title">`, удалены устаревшие CSS-правила `.testplan-section-link`.
  - В `tcms/testplans/static/testplans/js/get.js` логика инициализации заголовка переведена на `.js-section-title` без установки `href`.
  - Бандл Webpack пересобран (`npx webpack`), синхронизирован с рабочим Docker-контейнером `kiwi-local-web-1`.
  - Линтинг ESLint пройден без замечаний (0 ошибок).

