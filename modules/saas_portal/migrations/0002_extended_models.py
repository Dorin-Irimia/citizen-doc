from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0024_citizen_leave_enabled"),
        ("saas_portal", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="module_docs/")),
                ("original_name", models.CharField(blank=True, max_length=255)),
                ("mime_type", models.CharField(blank=True, max_length=100)),
                ("size", models.PositiveIntegerField(default=0)),
                ("sha256", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("municipality", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="module_documents", to="core.municipality")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="module_documents", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AssetEventDiff",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("field_path", models.CharField(max_length=200)),
                ("old_value", models.TextField(blank=True)),
                ("new_value", models.TextField(blank=True)),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="diffs", to="saas_portal.assetevent")),
            ],
        ),
        migrations.CreateModel(
            name="AssetRight",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("right_type", models.CharField(choices=[("own", "Proprietate"), ("use", "Folosinta"), ("lease", "Arenda/Chirie"), ("concession", "Concesiune")], max_length=20)),
                ("share", models.DecimalField(blank=True, decimal_places=3, help_text="Cota parte (0-1)", max_digits=6, null=True)),
                ("valid_from", models.DateField(default=django.utils.timezone.now)),
                ("valid_to", models.DateField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rights", to="saas_portal.asset")),
                ("document", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="rights", to="saas_portal.document")),
                ("holder", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="asset_rights", to="core.citizen")),
            ],
            options={
                "ordering": ["-valid_from"],
            },
        ),
        migrations.CreateModel(
            name="CaseFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("case_type", models.CharField(choices=[("declaration", "Declaratie bun"), ("complaint", "Sesizare"), ("other", "Alt tip")], default="declaration", max_length=30)),
                ("reg_no", models.CharField(blank=True, max_length=50)),
                ("reg_date", models.DateField(default=django.utils.timezone.now)),
                ("status", models.CharField(default="open", max_length=20)),
                ("sla_due_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("municipality", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="case_files", to="core.municipality")),
                ("requester", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="case_files", to="core.citizen")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CaseStep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("step_type", models.CharField(default="review", max_length=30)),
                ("status", models.CharField(default="open", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="case_steps", to=settings.AUTH_USER_MODEL)),
                ("case_file", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="steps", to="saas_portal.casefile")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="FiscalAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("opened_at", models.DateField(default=django.utils.timezone.now)),
                ("status", models.CharField(default="active", max_length=20)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("citizen", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fiscal_accounts", to="core.citizen")),
                ("municipality", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fiscal_accounts", to="core.municipality")),
            ],
            options={
                "ordering": ["municipality__name", "citizen__full_name"],
                "unique_together": {("municipality", "citizen")},
            },
        ),
        migrations.CreateModel(
            name="Household",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=50)),
                ("name", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("head", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="headed_households", to="core.citizen")),
                ("municipality", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="households", to="core.municipality")),
            ],
            options={
                "ordering": ["municipality__name", "code"],
                "unique_together": {("municipality", "code")},
            },
        ),
        migrations.CreateModel(
            name="TaxRuleSet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("version", models.CharField(default="v1", max_length=20)),
                ("valid_from", models.DateField(default=django.utils.timezone.now)),
                ("valid_to", models.DateField(blank=True, null=True)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("municipality", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tax_rule_sets", to="core.municipality")),
            ],
            options={
                "ordering": ["municipality__name", "-valid_from"],
            },
        ),
        migrations.CreateModel(
            name="HouseholdMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(blank=True, max_length=50)),
                ("valid_from", models.DateField(default=django.utils.timezone.now)),
                ("valid_to", models.DateField(blank=True, null=True)),
                ("citizen", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="household_memberships", to="core.citizen")),
                ("household", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="members", to="saas_portal.household")),
            ],
            options={
                "ordering": ["household", "-valid_from"],
            },
        ),
        migrations.CreateModel(
            name="HouseholdAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("relation_type", models.CharField(default="uses", max_length=50)),
                ("valid_from", models.DateField(default=django.utils.timezone.now)),
                ("valid_to", models.DateField(blank=True, null=True)),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="household_links", to="saas_portal.asset")),
                ("household", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assets", to="saas_portal.household")),
            ],
            options={
                "ordering": ["household", "-valid_from"],
            },
        ),
        migrations.CreateModel(
            name="TaxAssessment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tax_type", models.CharField(default="general", max_length=50)),
                ("period_year", models.PositiveIntegerField(default=django.utils.timezone.now().year)),
                ("base_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("rate", models.DecimalField(decimal_places=4, default=0, max_digits=6)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("explanation", models.JSONField(blank=True, default=dict)),
                ("issued_at", models.DateField(blank=True, null=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("issued", "Emisa"), ("cancelled", "Anulata")], default="draft", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("asset", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assessments", to="saas_portal.asset")),
                ("fiscal_account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assessments", to="saas_portal.fiscalaccount")),
            ],
            options={
                "ordering": ["-period_year", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("channel", models.CharField(default="manual", max_length=30)),
                ("provider_ref", models.CharField(blank=True, max_length=100)),
                ("initiated_at", models.DateTimeField(auto_now_add=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(default="initiated", max_length=20)),
                ("note", models.TextField(blank=True)),
                ("citizen", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="core.citizen")),
                ("municipality", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="core.municipality")),
            ],
            options={
                "ordering": ["-initiated_at"],
            },
        ),
        migrations.CreateModel(
            name="EventDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="event_links", to="saas_portal.document")),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documents", to="saas_portal.assetevent")),
            ],
        ),
        migrations.CreateModel(
            name="DebtItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("due_date", models.DateField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("paid_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("status", models.CharField(default="open", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("assessment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="debts", to="saas_portal.taxassessment")),
            ],
            options={
                "ordering": ["due_date"],
            },
        ),
        migrations.CreateModel(
            name="PaymentAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("debt_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocations", to="saas_portal.debtitem")),
                ("payment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocations", to="saas_portal.payment")),
            ],
            options={
                "ordering": ["payment"],
            },
        ),
    ]

