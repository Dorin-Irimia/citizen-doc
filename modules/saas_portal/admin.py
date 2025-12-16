from django.contrib import admin

from .models import (
    Asset,
    AssetEvent,
    AssetEventDiff,
    AssetRight,
    AssetType,
    CaseFile,
    CaseStep,
    DebtItem,
    Document,
    EventDocument,
    FiscalAccount,
    Household,
    HouseholdAsset,
    HouseholdMember,
    Payment,
    PaymentAllocation,
    TaxAssessment,
    TaxRuleSet,
)


@admin.register(AssetType)
class AssetTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "municipality", "code", "is_active", "created_at")
    list_filter = ("municipality", "is_active")
    search_fields = ("name", "code", "municipality__name")


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "asset_type",
        "municipality",
        "owner",
        "status",
        "effective_date",
        "created_at",
    )
    list_filter = ("status", "municipality", "asset_type")
    search_fields = ("title", "identifier", "owner__full_name")
    autocomplete_fields = ("owner", "asset_type", "municipality")


@admin.register(AssetEvent)
class AssetEventAdmin(admin.ModelAdmin):
    list_display = ("asset", "event_type", "actor", "created_at")
    list_filter = ("event_type",)
    search_fields = ("asset__title", "note", "actor__username")


@admin.register(AssetEventDiff)
class AssetEventDiffAdmin(admin.ModelAdmin):
    list_display = ("event", "field_path", "old_value", "new_value")
    search_fields = ("field_path", "old_value", "new_value")


@admin.register(AssetRight)
class AssetRightAdmin(admin.ModelAdmin):
    list_display = ("asset", "holder", "right_type", "valid_from", "valid_to")
    list_filter = ("right_type",)
    autocomplete_fields = ("asset", "holder", "document")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "municipality", "uploaded_by", "created_at")
    search_fields = ("original_name", "file")
    autocomplete_fields = ("municipality", "uploaded_by")


@admin.register(EventDocument)
class EventDocumentAdmin(admin.ModelAdmin):
    list_display = ("event", "document")
    autocomplete_fields = ("event", "document")


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("code", "municipality", "head", "created_at")
    search_fields = ("code", "head__full_name")
    autocomplete_fields = ("municipality", "head")


@admin.register(HouseholdMember)
class HouseholdMemberAdmin(admin.ModelAdmin):
    list_display = ("household", "citizen", "role", "valid_from", "valid_to")
    autocomplete_fields = ("household", "citizen")


@admin.register(HouseholdAsset)
class HouseholdAssetAdmin(admin.ModelAdmin):
    list_display = ("household", "asset", "relation_type", "valid_from", "valid_to")
    autocomplete_fields = ("household", "asset")


@admin.register(FiscalAccount)
class FiscalAccountAdmin(admin.ModelAdmin):
    list_display = ("citizen", "municipality", "status", "opened_at")
    search_fields = ("citizen__full_name",)
    autocomplete_fields = ("citizen", "municipality")


@admin.register(TaxRuleSet)
class TaxRuleSetAdmin(admin.ModelAdmin):
    list_display = ("name", "municipality", "version", "valid_from", "is_active")
    list_filter = ("municipality", "is_active")
    autocomplete_fields = ("municipality",)


@admin.register(TaxAssessment)
class TaxAssessmentAdmin(admin.ModelAdmin):
    list_display = ("fiscal_account", "period_year", "tax_type", "amount", "status")
    list_filter = ("status", "period_year", "tax_type")
    autocomplete_fields = ("fiscal_account", "asset")


@admin.register(DebtItem)
class DebtItemAdmin(admin.ModelAdmin):
    list_display = ("assessment", "due_date", "amount", "paid_amount", "status")
    list_filter = ("status",)
    autocomplete_fields = ("assessment",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("citizen", "municipality", "amount", "status", "initiated_at")
    list_filter = ("status", "municipality")
    autocomplete_fields = ("citizen", "municipality")


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ("payment", "debt_item", "amount")
    autocomplete_fields = ("payment", "debt_item")


@admin.register(CaseFile)
class CaseFileAdmin(admin.ModelAdmin):
    list_display = ("reg_no", "case_type", "municipality", "status", "reg_date")
    list_filter = ("case_type", "status", "municipality")
    autocomplete_fields = ("municipality", "requester")


@admin.register(CaseStep)
class CaseStepAdmin(admin.ModelAdmin):
    list_display = ("case_file", "step_type", "status", "assigned_to", "created_at")
    list_filter = ("step_type", "status")
    autocomplete_fields = ("case_file", "assigned_to")
