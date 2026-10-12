from django.db import migrations, models


def preserve_sibling_order(apps, schema_editor):
    plans = apps.get_model("testplans", "TestPlan")
    siblings = {}
    batch = []
    for plan in (
        plans.objects.using(schema_editor.connection.alias).order_by("pk").iterator()
    ):
        siblings[plan.parent_id] = siblings.get(plan.parent_id, 0) + 10
        plan.position = siblings[plan.parent_id]
        batch.append(plan)
        if len(batch) == 500:
            plans.objects.using(schema_editor.connection.alias).bulk_update(
                batch, ["position"]
            )
            batch = []
    if batch:
        plans.objects.using(schema_editor.connection.alias).bulk_update(
            batch, ["position"]
        )


class Migration(migrations.Migration):
    dependencies = [("testplans", "0013_russian_model_titles")]

    operations = [
        migrations.AddField(
            model_name="testplan",
            name="position",
            field=models.PositiveIntegerField(
                db_index=True, default=0, editable=False, verbose_name="Section order"
            ),
        ),
        migrations.AddField(
            model_name="historicaltestplan",
            name="position",
            field=models.PositiveIntegerField(
                db_index=True, default=0, editable=False, verbose_name="Section order"
            ),
        ),
        migrations.RunPython(preserve_sibling_order, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="testplan",
            options={
                "ordering": ["position", "pk"],
                "verbose_name": "Test plan",
                "verbose_name_plural": "Test plans",
            },
        ),
    ]
