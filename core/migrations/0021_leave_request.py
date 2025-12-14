from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_workitem_manual_html_staffnotification"),
    ]

    operations = [
        migrations.AddField(
            model_name="citizen",
            name="annual_leave_days",
            field=models.PositiveIntegerField(default=21),
        ),
        migrations.AddField(
            model_name="citizen",
            name="contract_start",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="LeaveRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("days_requested", models.PositiveIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "In asteptare"), ("approved", "Aprobat"), ("rejected", "Respins")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("note", models.TextField(blank=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "citizen",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="leave_requests",
                        to="core.citizen",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="leave_created_by",
                        to="auth.user",
                    ),
                ),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="leave_decided_by",
                        to="auth.user",
                    ),
                ),
                (
                    "municipality",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="leave_requests",
                        to="core.municipality",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
