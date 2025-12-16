from importlib import import_module

from django.conf import settings
from django.urls import include, path

# Discover enabled module apps from settings and mount their URL configs.
urlpatterns = []

for module_path in getattr(settings, "ENABLED_MODULES", []):
    try:
        urls_mod = import_module(f"{module_path}.urls")
    except ModuleNotFoundError:
        continue

    namespace = getattr(urls_mod, "app_name", module_path.split(".")[-1])
    mount = getattr(urls_mod, "MODULE_SLUG", namespace)

    urlpatterns.append(
        path(
            f"{mount}/",
            include((urls_mod.urlpatterns, namespace), namespace=namespace),
        )
    )

