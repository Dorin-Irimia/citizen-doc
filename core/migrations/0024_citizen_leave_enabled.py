from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_alter_staffnotification_work_item"),
    ]

    operations = [
        migrations.AddField(
            model_name="citizen",
            name="leave_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
