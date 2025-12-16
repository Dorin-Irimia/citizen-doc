from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from core.models import Citizen, Municipality

User = get_user_model()


class Document(models.Model):
    municipality = models.ForeignKey(
        Municipality,
        on_delete=models.CASCADE,
        related_name="module_documents",
    )
    uploaded_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="module_documents",
    )
    file = models.FileField(upload_to="module_docs/")
    original_name = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name or self.file.name


class AssetType(models.Model):
    municipality = models.ForeignKey(
        Municipality,
        on_delete=models.CASCADE,
        related_name="asset_types",
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    required_fields = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("municipality", "code")
        ordering = ["municipality__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.municipality})"


class Asset(models.Model):
    STATUS_CHOICES = [
        ("pending", "In validare"),
        ("active", "Activ"),
        ("rejected", "Respins"),
        ("archived", "Arhivat"),
    ]

    municipality = models.ForeignKey(
        Municipality,
        on_delete=models.CASCADE,
        related_name="assets",
    )
    owner = models.ForeignKey(
        Citizen,
        on_delete=models.CASCADE,
        related_name="assets",
    )
    asset_type = models.ForeignKey(
        AssetType,
        on_delete=models.PROTECT,
        related_name="assets",
    )
    title = models.CharField(max_length=200)
    identifier = models.CharField(max_length=100, null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    area_size = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Suprafata / dimensiune (opțional).",
    )
    extra_data = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    effective_date = models.DateField(default=timezone.now)
    note = models.TextField(blank=True)
    declared_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="declared_assets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("municipality", "identifier")

    def __str__(self):
        return self.title


class AssetEvent(models.Model):
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="events"
    )
    event_type = models.CharField(max_length=50)
    actor = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="asset_events"
    )
    payload = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} @ {self.asset}"


class AssetEventDiff(models.Model):
    event = models.ForeignKey(
        AssetEvent, on_delete=models.CASCADE, related_name="diffs"
    )
    field_path = models.CharField(max_length=200)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)

    def __str__(self):
        return f"{self.field_path}: {self.old_value} -> {self.new_value}"


class AssetRight(models.Model):
    RIGHT_CHOICES = [
        ("own", "Proprietate"),
        ("use", "Folosinta"),
        ("lease", "Arenda/Chirie"),
        ("concession", "Concesiune"),
    ]
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="rights"
    )
    holder = models.ForeignKey(
        Citizen, on_delete=models.CASCADE, related_name="asset_rights"
    )
    right_type = models.CharField(max_length=20, choices=RIGHT_CHOICES)
    share = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True, help_text="Cota parte (0-1)"
    )
    valid_from = models.DateField(default=timezone.now)
    valid_to = models.DateField(null=True, blank=True)
    document = models.ForeignKey(
        Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="rights"
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-valid_from"]

    def __str__(self):
        return f"{self.asset} - {self.get_right_type_display()}"


class Household(models.Model):
    municipality = models.ForeignKey(
        Municipality, on_delete=models.CASCADE, related_name="households"
    )
    code = models.CharField(max_length=50)
    head = models.ForeignKey(
        Citizen,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="headed_households",
    )
    name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("municipality", "code")
        ordering = ["municipality__name", "code"]

    def __str__(self):
        return self.name or self.code


class HouseholdMember(models.Model):
    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="members"
    )
    citizen = models.ForeignKey(
        Citizen, on_delete=models.CASCADE, related_name="household_memberships"
    )
    role = models.CharField(max_length=50, blank=True)
    valid_from = models.DateField(default=timezone.now)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["household", "-valid_from"]

    def __str__(self):
        return f"{self.citizen} @ {self.household}"


class HouseholdAsset(models.Model):
    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="assets"
    )
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="household_links"
    )
    relation_type = models.CharField(max_length=50, default="uses")
    valid_from = models.DateField(default=timezone.now)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["household", "-valid_from"]

    def __str__(self):
        return f"{self.asset} @ {self.household}"


class FiscalAccount(models.Model):
    municipality = models.ForeignKey(
        Municipality, on_delete=models.CASCADE, related_name="fiscal_accounts"
    )
    citizen = models.ForeignKey(
        Citizen, on_delete=models.CASCADE, related_name="fiscal_accounts"
    )
    opened_at = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, default="active")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("municipality", "citizen")
        ordering = ["municipality__name", "citizen__full_name"]

    def __str__(self):
        return f"Cont fiscal {self.citizen}"


class TaxRuleSet(models.Model):
    municipality = models.ForeignKey(
        Municipality, on_delete=models.CASCADE, related_name="tax_rule_sets"
    )
    name = models.CharField(max_length=150)
    version = models.CharField(max_length=20, default="v1")
    valid_from = models.DateField(default=timezone.now)
    valid_to = models.DateField(null=True, blank=True)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["municipality__name", "-valid_from"]

    def __str__(self):
        return f"{self.name} ({self.version})"


class TaxAssessment(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("issued", "Emisa"),
        ("cancelled", "Anulata"),
    ]
    fiscal_account = models.ForeignKey(
        FiscalAccount, on_delete=models.CASCADE, related_name="assessments"
    )
    asset = models.ForeignKey(
        Asset, null=True, blank=True, on_delete=models.SET_NULL, related_name="assessments"
    )
    tax_type = models.CharField(max_length=50, default="general")
    period_year = models.PositiveIntegerField(default=timezone.now().year)
    base_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rate = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    explanation = models.JSONField(default=dict, blank=True)
    issued_at = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_year", "-created_at"]

    def __str__(self):
        return f"Impunere {self.period_year} - {self.fiscal_account}"


class DebtItem(models.Model):
    assessment = models.ForeignKey(
        TaxAssessment, on_delete=models.CASCADE, related_name="debts"
    )
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, default="open")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date"]

    def __str__(self):
        return f"Scadenta {self.due_date} - {self.amount}"


class Payment(models.Model):
    municipality = models.ForeignKey(
        Municipality, on_delete=models.CASCADE, related_name="payments"
    )
    citizen = models.ForeignKey(
        Citizen, on_delete=models.CASCADE, related_name="payments"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    channel = models.CharField(max_length=30, default="manual")
    provider_ref = models.CharField(max_length=100, blank=True)
    initiated_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default="initiated")
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-initiated_at"]

    def __str__(self):
        return f"Plata {self.amount} ({self.status})"


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="allocations"
    )
    debt_item = models.ForeignKey(
        DebtItem, on_delete=models.CASCADE, related_name="allocations"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["payment"]

    def __str__(self):
        return f"{self.amount} -> {self.debt_item}"


class CaseFile(models.Model):
    CASE_CHOICES = [
        ("declaration", "Declaratie bun"),
        ("complaint", "Sesizare"),
        ("other", "Alt tip"),
    ]
    municipality = models.ForeignKey(
        Municipality, on_delete=models.CASCADE, related_name="case_files"
    )
    requester = models.ForeignKey(
        Citizen, null=True, blank=True, on_delete=models.SET_NULL, related_name="case_files"
    )
    case_type = models.CharField(max_length=30, choices=CASE_CHOICES, default="declaration")
    reg_no = models.CharField(max_length=50, blank=True)
    reg_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, default="open")
    sla_due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reg_no or f"Dosar {self.id}"


class CaseStep(models.Model):
    case_file = models.ForeignKey(
        CaseFile, on_delete=models.CASCADE, related_name="steps"
    )
    step_type = models.CharField(max_length=30, default="review")
    status = models.CharField(max_length=20, default="open")
    assigned_to = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="case_steps"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.step_type} ({self.status})"
