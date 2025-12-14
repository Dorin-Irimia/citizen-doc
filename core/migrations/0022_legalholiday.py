from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_leave_request"),
    ]

    operations = [
        migrations.CreateModel(
            name="LegalHoliday",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("date", models.DateField()),
                ("label", models.CharField(max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "municipality",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="legal_holidays",
                        to="core.municipality",
                    ),
                ),
            ],
            options={
                "ordering": ["date"],
            },
        ),
        migrations.AddConstraint(
            model_name="legalholiday",
            constraint=models.UniqueConstraint(
                fields=("date", "municipality"), name="unique_holiday_per_muni_or_global"
            ),
        ),
    ]
