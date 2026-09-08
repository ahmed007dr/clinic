import uuid

from django.db import migrations, models

MODELS = ["Branch"]


def assign_uuids(apps, schema_editor):
    """A fresh UUID per row.

    AddField with default=uuid.uuid4 evaluates the callable once and writes
    that same value to every existing row, so the unique constraint has to be
    applied only after each row has its own value.
    """
    for model_name in MODELS:
        model = apps.get_model("branches", model_name)
        batch = []
        for row in model.objects.filter(uuid__isnull=True).iterator():
            row.uuid = uuid.uuid4()
            batch.append(row)
            if len(batch) >= 500:
                model.objects.bulk_update(batch, ["uuid"])
                batch = []
        if batch:
            model.objects.bulk_update(batch, ["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0004_alter_branch_options_alter_branch_managers"),
    ]

    operations = (
        [
            migrations.AddField(
                model_name=m.lower(),
                name="uuid",
                field=models.UUIDField(editable=False, null=True),
            )
            for m in MODELS
        ]
        + [migrations.RunPython(assign_uuids, migrations.RunPython.noop)]
        + [
            migrations.AlterField(
                model_name=m.lower(),
                name="uuid",
                field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
            )
            for m in MODELS
        ]
    )
