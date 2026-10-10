# Локальный запуск Kiwi SPI на Windows

Исходники: https://github.com/DaTsan/Kiwi-SPI, папка `C:\Users\prode\Desktop\kiwi`.

Окружение собирает именно эту модификацию из исходников: Python 3.12, Node.js 24
(для сборки JavaScript) и MariaDB 11.4. На Windows требуется Docker Desktop
с запущенным Linux engine. Python и Node.js отдельно устанавливать не нужно.

## Запуск

Дважды нажмите **start-local.cmd**. Или выполните в PowerShell:

```powershell
cd C:\Users\prode\Desktop\kiwi
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-local.ps1
```

Первый запуск скачивает зависимости, собирает образ, применяет миграции и создает
администратора. Следующие сборки используют Docker-кеш. Для запуска без сборки:

```powershell
.\start-local.ps1 -NoBuild
```

Откройте **http://127.0.0.1:8000**. Логин — `admin`, пароль — значение
`KIWI_ADMIN_PASSWORD` в `.env.local`. Этот файл создается автоматически при первом
запуске и не попадает в Git или Docker-образ. При последующих запусках пароль
существующего администратора не сбрасывается.

## Остановка и данные

Дважды нажмите **stop-local.cmd** или выполните `.\stop-local.ps1`.
База и вложения сохраняются в Docker-томах `kiwi-spi-local_db_data` и
`kiwi-spi-local_uploads`. Не удаляйте эти тома, если хотите сохранить данные.
Для полной остановки ПК достаточно штатно завершить работу Windows.

## Диагностика и обслуживание

```powershell
docker compose --env-file .env.local -f compose.local.yaml ps
docker compose --env-file .env.local -f compose.local.yaml logs --tail 100
docker compose --env-file .env.local -f compose.local.yaml exec web python manage.py check
docker compose --env-file .env.local -f compose.local.yaml exec web python manage.py changepassword admin
```

После редактирования исходников снова запустите `start-local.cmd`, чтобы
пересобрать образ. Смена пароля через `changepassword` сохраняется в базе;
значение в `.env.local` используется только при создании нового администратора.

Это локальное окружение с Django runserver и DEBUG для работы на этом ПК.
Порт опубликован только на `127.0.0.1:8000`, база наружу не публикуется.
Отправка писем выводится в логи контейнера. Для размещения в сети нужно отдельное
окружение с рабочим веб-сервером и HTTPS.

Используйте `compose.local.yaml`: исходный `docker-compose.yml` запускает
готовый upstream-образ Kiwi, без изменений из Kiwi-SPI.

## Проверено на этом ПК

Исходный коммит: `624f819c8` (ветка `master`). Сборка образа, все миграции,
вход администратором, поиск планов/кейсов/запусков и 32 статических файла
прошли проверку. После остановки и запуска сохранились база, пароль
администратора и файл в томе вложений; временный проверочный файл удален.

Проверенный адрес Windows — `127.0.0.1:8000`. Обращение через имя `localhost`
на этом ПК дает тайм-аут, поэтому в инструкции указан прямой адрес.

## Новое планирование и выполнение

Раздел WORKFLOW: http://127.0.0.1:8000/workflow/.
Рабочий маршрут и ограничения: [WORKFLOW-GUIDE.md](WORKFLOW-GUIDE.md).
Анализ TestRail и план следующих этапов: [TESTRAIL-GAP-ANALYSIS.md](TESTRAIL-GAP-ANALYSIS.md).
Проверки новой реализации: [IMPLEMENTATION-REPORT.md](IMPLEMENTATION-REPORT.md).
