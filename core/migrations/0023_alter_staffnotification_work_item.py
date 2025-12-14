from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_legalholiday"),
    ]

    operations = [
        migrations.AlterField(
            model_name="staffnotification",
            name="work_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications",
                to="core.workitem",
            ),
        ),
    ]
