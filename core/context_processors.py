from .models import Notification, StaffNotification

def unread_counts(request):
    data = {
        "unread_citizen": 0,
        "unread_staff": 0,
    }
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"unread_counts": data}
    if hasattr(user, "citizen_profile"):
        ctz = user.citizen_profile
        data["unread_citizen"] = Notification.objects.filter(citizen=ctz, is_read=False).count()
    if user.is_staff:
        data["unread_staff"] = StaffNotification.objects.filter(user=user, is_read=False).count()
    return {"unread_counts": data}
