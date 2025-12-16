from django.urls import path

from . import views

app_name = "saas_portal"
MODULE_SLUG = "portal"

urlpatterns = [
    path("", views.portal_home, name="home"),
    path("assets/", views.asset_list, name="asset_list"),
    path("assets/new/", views.asset_submit, name="asset_submit"),
    path("assets/<int:pk>/", views.asset_detail, name="asset_detail"),
    path("assets/<int:pk>/review/", views.asset_review, name="asset_review"),
    path("types/", views.asset_type_list, name="asset_type_list"),
    path("types/new/", views.asset_type_create, name="asset_type_create"),
    path("ra/", views.ra_dashboard, name="ra_dashboard"),
    path("fiscal/", views.fiscal_dashboard, name="fiscal_dashboard"),
]
