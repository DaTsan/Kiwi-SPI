import csv
import io
import json
import re
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.loader import get_template
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils.translation import gettext, ngettext, override, pgettext

from tcms.workflow.forms import CustomValuesForm, StepForm
from tcms.workflow.models import Milestone, SharedStepSet
from tcms.workflow.services import record_result
from tcms.workflow.templatetags.workflow import display_value
from tcms.workflow.validators import validate_steps

from .base import WorkflowTestCase


class RussianCatalogTests(SimpleTestCase):
    def test_both_catalogs_have_no_untranslated_or_fuzzy_messages(self):
        for domain in ("django", "djangojs"):
            path = (
                Path(settings.TCMS_ROOT_PATH)
                / "locale/ru_RU/LC_MESSAGES"
                / f"{domain}.po"
            )
            for flag in ("--untranslated", "--only-fuzzy"):
                with self.subTest(domain=domain, flag=flag):
                    result = subprocess.run(
                        ["msgattrib", flag, "--no-obsolete", str(path)],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotRegex(
                        result.stdout,
                        re.compile(r'^msgid "(?:[^"\n]+|"\n")', re.M),
                        msg=path,
                    )
            self.assertNotIn("\ufffd", path.read_text(encoding="utf-8"))

    def test_russian_language_variants_load_the_project_catalog(self):
        for language in ("ru", "ru-ru"):
            with self.subTest(language=language), override(language):
                self.assertEqual(gettext("Planning"), "Планирование")
                self.assertEqual(gettext("Structured steps"), "Структурированные шаги")
                self.assertEqual(gettext("PASSED"), "ПРОЙДЕНО")
                self.assertEqual(
                    gettext("- Select an option -"), "— Выберите вариант —"
                )
                self.assertEqual(
                    pgettext("custom field type", "Select"), "Список выбора"
                )
                self.assertEqual(str(Milestone.Status.UPCOMING.label), "Запланирован")

    def test_russian_plural_rules(self):
        for count, suffix in (
            (0, "шагов"),
            (1, "шаг"),
            (2, "шага"),
            (5, "шагов"),
            (11, "шагов"),
            (21, "шаг"),
            (22, "шага"),
        ):
            with self.subTest(count=count), override("ru"):
                text = ngettext("%(count)s step", "%(count)s steps", count) % {
                    "count": count
                }
                self.assertEqual(text, f"{count} {suffix}")

    def test_all_project_templates_compile(self):
        for path in Path(settings.TCMS_ROOT_PATH).rglob("templates/**/*.html"):
            if "node_modules" in path.parts:
                continue
            name = str(path).split("templates/", 1)[1]
            with self.subTest(template=name):
                get_template(name)

    @override_settings(MIDDLEWARE=["django.middleware.locale.LocaleMiddleware"])
    def test_javascript_catalog_is_translated_and_english_still_works(self):
        for language, label in (
            ("ru", "Настроить интерфейс"),
            ("ru-ru", "Настроить интерфейс"),
        ):
            response = self.client.get(
                reverse("javascript-catalog"), HTTP_ACCEPT_LANGUAGE=language
            )
            self.assertEqual(response.status_code, 200)
            # JavaScriptCatalog serializes non-ASCII strings using JSON escapes.
            match = re.search(
                r'"Customize layout": ("(?:\\.|[^"\\])*")', response.content.decode()
            )
            self.assertIsNotNone(match)
            self.assertEqual(json.loads(match[1]), label)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        response = self.client.get(reverse("javascript-catalog"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "\\u041d\\u0430\\u0441\\u0442\\u0440", response.content.decode()
        )

    def test_translated_validation_and_boolean_values(self):
        with override("ru"):
            self.assertEqual(
                str(StepForm.base_fields["expected"].label), "Ожидаемый результат"
            )
            with self.assertRaisesMessage(
                ValidationError, "В каждом шаге должно быть действие"
            ):
                validate_steps([{"action": ""}])
            self.assertEqual(display_value(True), "Да")
            self.assertEqual(display_value(False), "Нет")
            self.assertEqual(display_value("User-entered value"), "User-entered value")


class RussianInterfaceTests(WorkflowTestCase):
    def setUp(self):
        self.client.force_login(self.user)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"

    def test_core_and_workflow_pages_render_in_russian(self):
        pages = [
            ("/", "Планирование и этапы"),
            (reverse("plans-search"), "Поиск"),
            (reverse("testcases-search"), "Поиск"),
            (reverse("testruns-search"), "Поиск"),
            (self.case.get_absolute_url(), "Шаги и пользовательские поля"),
            (
                self.test_run.get_absolute_url(),
                "Выполнение шагов, результаты и планирование",
            ),
            (reverse("workflow:hub"), "Библиотека общих шагов"),
            (reverse("workflow:milestone-new"), "Родительский этап"),
            (reverse("workflow:cycle", args=[self.cycle.pk]), "Создать прогоны"),
            (reverse("workflow:shared-new"), "Добавить шаг / общий набор"),
            (reverse("workflow:field-new"), "Варианты выбора"),
            (reverse("workflow:case", args=[self.case.pk]), "Сохранить шаги и поля"),
            (
                reverse("workflow:execution", args=[self.execution.pk]),
                "Сохранить результат",
            ),
            (
                reverse("workflow:run", args=[self.test_run.pk]),
                "Сохранить планирование",
            ),
            (reverse("workflow:todo"), "Мои задачи"),
            (reverse("workflow:report"), "Экспорт CSV"),
            (reverse("admin:index"), "Управление продуктами"),
            (reverse("admin:management_product_add"), "Классификация"),
            (reverse("admin:workflow_milestone_add"), "Родительский этап"),
            (reverse("admin:testruns_environment_add"), "Окружение"),
            (reverse("admin:testruns_testexecutionstatus_add"), "Цвет"),
        ]
        for url, expected in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, expected)
                self.assertEqual(response.headers["Content-Language"], "ru")
        response = self.client.get(reverse("workflow:field-new"))
        self.assertContains(response, "— Выберите вариант —")
        self.assertContains(response, "Список выбора")
        self.assertNotContains(response, "- Select an option -")

    def test_language_switch_keeps_filters_and_cookie_overrides_browser(self):
        url = (
            reverse("workflow:report")
            + f"?product={self.product.pk}&cycle={self.cycle.pk}"
        )
        response = self.client.post(
            reverse("set_language"), {"language": "en", "next": url}
        )
        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "en")
        self.assertContains(
            self.client.get(url, HTTP_ACCEPT_LANGUAGE="ru"), "Export CSV"
        )
        self.client.post(reverse("set_language"), {"language": "ru", "next": url})
        response = self.client.get(url, HTTP_ACCEPT_LANGUAGE="en")
        self.assertContains(response, "Экспорт CSV")
        self.assertContains(response, 'name="cycle"')

    def test_language_switch_requires_csrf_and_rejects_external_redirects(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse("set_language")
        self.assertEqual(client.post(url, {"language": "ru"}).status_code, 403)
        client.get(reverse("tcms-login"))
        response = client.post(
            url,
            {
                "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
                "language": "ru",
                "next": "https://example.org/outside",
            },
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    @override_settings(LANGUAGE_CODE="ru")
    def test_login_defaults_to_russian_without_a_language_cookie(self):
        response = Client().get(reverse("tcms-login"))
        self.assertEqual(response.headers["Content-Language"], "ru")
        self.assertContains(response, "Язык интерфейса")

    def test_csv_headers_are_russian_and_user_content_is_preserved(self):
        response = self.client.get(reverse("workflow:report"), {"format": "csv"})
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(
            rows[0][0:5],
            ["ID прогона", "Прогон", "ID выполнения", "ID тест-кейса", "Тест-кейс"],
        )
        self.assertEqual(rows[1][4], self.case.summary)

    def test_existing_result_status_is_translated_without_rewriting_history(self):
        with override("en"):
            result = record_result(
                self.user,
                self.execution.pk,
                status=self.passed,
                step_values=self.step_values(),
                elapsed_seconds=5,
                comment="Keep this comment",
            )
        label = result.status_label
        response = self.client.get(
            reverse("workflow:execution", args=[self.execution.pk])
        )
        self.assertContains(response, "ПРОЙДЕНО")
        self.assertContains(response, "Затрачено: 5 секунд")
        self.assertContains(response, "Keep this comment")
        result.refresh_from_db()
        self.assertEqual(result.status_label, label)

    def test_shared_step_count_is_rendered_with_russian_plural(self):
        SharedStepSet.objects.create(
            product=self.product,
            name="User library",
            steps=[{"action": "User action"}] * 2,
        )
        response = self.client.get(reverse("workflow:hub"))
        self.assertContains(response, "2 шага")
        self.assertContains(response, "User library")

    def test_custom_field_labels_are_user_content(self):
        field = self.field(key="user_text")
        field.label = "User-defined label"
        field.save()
        with override("ru"):
            form = CustomValuesForm(product_id=self.product.pk, entity="case")
            self.assertEqual(
                form.fields["custom_user_text"].label, "User-defined label"
            )
