from django.urls import path
from . import views

urlpatterns = [
    path("", views.generate_select, name="home"),

    # autentificare cetatean
    path("login/", views.citizen_login, name="citizen_login"),
    path("logout/", views.citizen_logout, name="citizen_logout"),
    path("superadmin/code/", views.superadmin_request_code, name="superadmin_request_code"),
    path("superadmin/verify/", views.superadmin_verify_code, name="superadmin_verify_code"),
    path("superadmin/overview/", views.superadmin_overview, name="superadmin_overview"),
    path("superadmin/municipality/new/", views.municipality_create, name="municipality_create"),
    path("superadmin/email-test/", views.superadmin_send_test_email, name="superadmin_send_test_email"),
    path("superadmin/admins/", views.superadmin_admins, name="superadmin_admins"),
    path("invites/new/", views.admin_invite_create, name="admin_invite_create"),
    path("invites/accept/<str:token>/", views.admin_invite_accept, name="admin_invite_accept"),
    path("forgot-password/", views.forgot_password_request, name="forgot_password_request"),
    path("forgot-password/verify/", views.forgot_password_verify, name="forgot_password_verify"),
    path("confirm-email/", views.confirm_email, name="confirm_email"),
    path("dashboard/", views.citizen_dashboard, name="citizen_dashboard"),
    path("profil/", views.citizen_self_edit, name="citizen_self_edit"),
    path("profil/send-email-code/", views.citizen_send_email_code, name="citizen_send_email_code"),
    path("cerere-document/", views.citizen_request_document, name="citizen_request_document"),
    # cont admin de primarie (evitam conflictul cu /admin/ din Django)
    path("staff/account/", views.admin_account, name="admin_account"),
    path("chat/", views.chat_thread, name="citizen_chat"),
    path("chat/<int:citizen_id>/", views.chat_thread, name="admin_chat"),

    # cetateni (administrare)
    path("citizens/", views.citizen_list, name="citizen_list"),
    path("citizens/new/", views.citizen_create, name="citizen_create"),
    path("citizens/<int:pk>/edit/", views.citizen_edit, name="citizen_edit"),
    path("citizens/<int:pk>/delete/", views.citizen_delete, name="citizen_delete"),

    # template-uri
    path("templates/", views.template_list, name="template_list"),
    path("templates/new/", views.template_create, name="template_create"),
    path("templates/<slug:slug>/edit/", views.template_edit, name="template_edit"),
    path("templates/<slug:slug>/delete/", views.template_delete, name="template_delete"),
    path("templates/fields/<int:pk>/delete/", views.dynamic_field_delete, name="dynamic_field_delete"),
    path("export/citizens/", views.export_citizens, name="export_citizens"),
    path("import/citizens/", views.import_citizens, name="import_citizens"),
    path("export/templates/", views.export_templates, name="export_templates"),
    path("import/templates/", views.import_templates, name="import_templates"),
    path("documents/<int:doc_id>/preview/", views.document_preview, name="document_preview"),
    path("work-items/", views.work_item_list, name="work_item_list"),
    path("work-items/<int:pk>/", views.work_item_detail, name="work_item_detail"),
    path("work-items/<int:pk>/delete/", views.work_item_delete, name="work_item_delete"),
    path("concedii/", views.leave_dashboard, name="leave_dashboard"),
    path("concedii/cetatean/", views.leave_citizen, name="leave_citizen"),

    # generare
    path("generate/", views.generate_select, name="generate_select"),
    path("generate/preview/", views.generate_preview, name="generate_preview"),
    path(
        "generate/<int:citizen_id>/<slug:template_slug>/",
        views.generate_document,
        name="generate_document",
    ),
]
