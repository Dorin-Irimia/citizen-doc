from django.contrib import admin
from .models import (
    Citizen,
    DocumentTemplate,
    ExtraFieldDefinition,
    ExtraFieldValue,
    GeneratedDocument,
    WorkItem,
    DynamicFieldLibrary,
    StaffNotification,
    Notification,
    Municipality,
    MunicipalityAdmin,
    AdminInvite,
    SuperAdminCode,
    Message,
    PasswordResetCode,
)


@admin.register(Citizen)
class CitizenAdmin(admin.ModelAdmin):
    list_display = ("full_name", "identifier", "cnp", "created_at")
    search_fields = ("full_name", "identifier", "cnp")


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "template_type", "output_type", "municipality_list", "created_at")
    search_fields = ("name", "slug", "municipalities__name")

    @admin.display(description="Primarii")
    def municipality_list(self, obj):
        names = obj.municipalities.values_list("name", flat=True)
        return ", ".join(names) if names else "Toate"


@admin.register(ExtraFieldDefinition)
class ExtraFieldDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "label", "created_at")
    search_fields = ("name", "label")


@admin.register(ExtraFieldValue)
class ExtraFieldValueAdmin(admin.ModelAdmin):
    list_display = ("citizen", "field_def", "value")
    search_fields = ("citizen__full_name", "field_def__name")


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(admin.ModelAdmin):
    list_display = ("template", "citizen", "output_type", "created_at")
    search_fields = ("template__name", "citizen__full_name")


@admin.register(WorkItem)
class WorkItemAdmin(admin.ModelAdmin):
    list_display = ("template", "citizen", "status", "created_at")
    search_fields = ("template__name", "citizen__full_name")


@admin.register(DynamicFieldLibrary)
class DynamicFieldLibraryAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "length", "created_at")
    search_fields = ("key", "label")

    def has_delete_permission(self, request, obj=None):
        return request.user and request.user.is_superuser


@admin.register(StaffNotification)
class StaffNotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "is_read", "created_at")
    search_fields = ("title", "user__username")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "citizen", "is_read", "created_at")
    search_fields = ("title", "citizen__full_name")


@admin.register(Municipality)
class MunicipalityAdminModel(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name", "slug")


@admin.register(MunicipalityAdmin)
class MunicipalityAdminAdmin(admin.ModelAdmin):
    list_display = ("user", "municipality", "created_at")
    search_fields = ("user__username", "municipality__name")


@admin.register(AdminInvite)
class AdminInviteAdmin(admin.ModelAdmin):
    list_display = ("email", "municipality", "used", "created_at")
    search_fields = ("email", "municipality__name", "token")


@admin.register(SuperAdminCode)
class SuperAdminCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "is_used", "created_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("citizen", "sender", "created_at")
    search_fields = ("citizen__full_name", "sender__username", "text")


@admin.register(PasswordResetCode)
class PasswordResetCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "used", "expires_at", "created_at")
    search_fields = ("user__username", "code")
