from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0025_tenant_portal_allow_other_branches'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='listed_in_directory',
            field=models.BooleanField(default=False),
        ),
    ]
