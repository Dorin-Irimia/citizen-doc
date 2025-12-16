from django.conf import settings
from django.urls import reverse

from .models import Notification, StaffNotification, Message, MunicipalityAdmin

def unread_counts(request):
    data = {
        "unread_citizen": 0,
        "unread_staff": 0,
        "unread_staff_leave": 0,
        "unread_chat_staff": 0,
    }
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"unread_counts": data}
    if hasattr(user, "citizen_profile"):
        ctz = user.citizen_profile
        data["unread_citizen"] = Notification.objects.filter(citizen=ctz, is_read=False).count()
    if user.is_staff:
        qs_staff = StaffNotification.objects.filter(user=user, is_read=False)
        data["unread_staff"] = qs_staff.count()
        data["unread_staff_leave"] = qs_staff.filter(work_item__isnull=True).count()
        muni = None
        if hasattr(user, "municipality_admin"):
            muni = user.municipality_admin.municipality
        chat_qs = Message.objects.filter(sender__is_staff=False, read_by_staff=False)
        if muni:
            chat_qs = chat_qs.filter(citizen__municipality=muni)
        data["unread_chat_staff"] = chat_qs.count()
    return {"unread_counts": data}


def optional_modules(request):
    enabled = getattr(settings, "ENABLED_MODULES", [])
    links = []
    if "modules.saas_portal" in enabled:
        try:
            links.append({"label": "Modular Hub", "url": reverse("saas_portal:home")})
        except Exception:
            # reverse can fail before URLconf is fully loaded; ignore in that case
            pass
    return {
        "enabled_modules": enabled,
        "module_links": links,
    }
