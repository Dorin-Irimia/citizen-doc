from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0024_citizen_leave_enabled"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssetType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=50)),
                ("name", models.CharField(max_length=150)),
                ("description", models.TextField(blank=True)),
                ("required_fields", models.JSONField(blank=True, default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("municipality", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="asset_types", to="core.municipality")),
            ],
            options={
                "ordering": ["municipality__name", "name"],
                "unique_together": {("municipality", "code")},
            },
        ),
        migrations.CreateModel(
            name="Asset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("identifier", models.CharField(blank=True, max_length=100, null=True)),
                ("location", models.CharField(blank=True, max_length=200)),
                ("area_size", models.DecimalField(blank=True, decimal_places=2, help_text="Suprafata / dimensiune (opțional).", max_digits=12, null=True)),
                ("extra_data", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("pending", "In validare"), ("active", "Activ"), ("rejected", "Respins"), ("archived", "Arhivat")], default="pending", max_length=20)),
                ("effective_date", models.DateField(default=django.utils.timezone.now)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("asset_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assets", to="saas_portal.assettype")),
                ("declared_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="declared_assets", to=settings.AUTH_USER_MODEL)),
                ("municipality", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assets", to="core.municipality")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assets", to="core.citizen")),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("municipality", "identifier")},
            },
        ),
        migrations.CreateModel(
            name="AssetEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=50)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="asset_events", to=settings.AUTH_USER_MODEL)),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="saas_portal.asset")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]

