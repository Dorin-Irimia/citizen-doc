import io
import secrets
import csv
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db import models
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import Context, Template
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from xhtml2pdf import pisa

from .forms import (
    CitizenForm,
    CitizenLoginForm,
    CitizenSelfForm,
    DocumentTemplateForm,
    ExtraFieldFormSet,
    AdminInviteForm,
    AdminAcceptForm,
    MunicipalityForm,
    SendTestEmailForm,
    SuperAdminRequestCodeForm,
    SuperAdminVerifyCodeForm,
    ForgotPasswordRequestForm,
    ForgotPasswordVerifyForm,
    ConfirmEmailForm,
    MunicipalityProfileForm,
    ImportCitizensForm,
    ImportTemplatesForm,
    parse_dynamic_fields,
)
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
    ChatThread,
    PasswordResetCode,
    EmailVerificationCode,
    LeaveRequest,
    LegalHoliday,
)


# Helpers -----------------------------------------------------------------


def _sync_user_account(citizen: Citizen, password: str | None = None):
    """
    Creeaza sau sincronizeaza user-ul pentru autentificare pe baza de CNP.
    Username = CNP; email nu este obligatoriu.
    """
    if not citizen.cnp:
        return citizen

    username = citizen.cnp
    user = citizen.user
    if user and user.username != username:
        user.username = username
    if not user:
        user, _ = User.objects.get_or_create(username=username)
        citizen.user = user

    if password:
        user.set_password(password)
    elif not user.has_usable_password():
        user.set_unusable_password()

    user.save()
    citizen.save(update_fields=["user"])
    return citizen


def _user_municipality(user):
    if not user.is_authenticated:
        return None
    if hasattr(user, "municipality_admin"):
        return user.municipality_admin.municipality
    return None


# ---- Cetateni -----------------------------------------------------------

@user_passes_test(lambda u: u.is_staff)
def citizen_list(request):
    muni = _user_municipality(request.user)
    qs = Citizen.objects.all().select_related("user")
    # adnotari pentru numarul de mesaje ne-citite trimise de cetatean
    qs = qs.annotate(
        msg_from_citizen=models.Count(
            "messages",
            filter=models.Q(messages__sender=models.F("user"), messages__read_by_staff=False),
        )
    )
    if muni:
        qs = qs.filter(municipality=muni)

    # filtre simple
    q = request.GET.get("q", "").strip()
    status_f = request.GET.get("status", "").strip()
    if q:
        qs = qs.filter(
            models.Q(full_name__icontains=q)
            | models.Q(cnp__icontains=q)
            | models.Q(identifier__icontains=q)
        )
    if status_f:
        qs = qs.filter(profile_status=status_f)

    # sortare
    sort = request.GET.get("sort", "")
    if sort == "messages":
        qs = qs.order_by("-msg_from_citizen", "full_name")
    else:
        qs = qs.order_by("full_name")

    if request.method == "POST":
        citizen_id = request.POST.get("citizen_id")
        new_status = request.POST.get("profile_status")
        if citizen_id and new_status:
            ctz = get_object_or_404(qs, pk=citizen_id)
            ctz.profile_status = new_status
            ctz.save(update_fields=["profile_status"])
            _notify_citizen(
                ctz,
                "Status profil actualizat",
                f"Statusul profilului tau este acum: {ctz.get_profile_status_display()}",
            )
            messages.success(request, "Status actualizat.")
            return redirect("citizen_list")
    citizens = qs
    status_choices = Citizen.STATUS_CHOICES
    return render(
        request,
        "core/citizen_list.html",
        {
            "citizens": citizens,
            "status_choices": status_choices,
            "q": q,
            "status_f": status_f,
            "sort": sort,
        },
    )


@user_passes_test(lambda u: u.is_staff)
def citizen_create(request):
    muni = _user_municipality(request.user)
    form = CitizenForm(request.POST or None, user=request.user)
    formset = ExtraFieldFormSet(request.POST or None, prefix="extra")

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        citizen = form.save(commit=False)
        if muni:
            citizen.municipality = muni
        citizen.save()
        password = form.cleaned_data.get("password1") or None
        _sync_user_account(citizen, password)
        _process_extra_fields(citizen, formset)
        messages.success(request, "Cetatean salvat.")
        return redirect("citizen_list")

    return render(
        request,
        "core/citizen_form.html",
        {"form": form, "formset": formset, "citizen": None, "self_edit": False},
    )


@user_passes_test(lambda u: u.is_staff)
def citizen_edit(request, pk):
    citizen = get_object_or_404(Citizen, pk=pk)
    muni = _user_municipality(request.user)
    if muni and citizen.municipality != muni:
        return HttpResponse(status=403)
    old_status = citizen.profile_status
    initial_extra = [
        {"field_name": val.field_def.name, "field_value": val.value}
        for val in citizen.extra_values.select_related("field_def")
    ]
    form = CitizenForm(request.POST or None, instance=citizen, user=request.user)
    formset = ExtraFieldFormSet(
        request.POST or None, prefix="extra", initial=initial_extra
    )

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        citizen_obj = form.save(commit=False)
        if muni:
            citizen_obj.municipality = muni
        citizen_obj.save()
        citizen = citizen_obj
        password = form.cleaned_data.get("password1") or None
        _sync_user_account(citizen, password)
        _process_extra_fields(citizen, formset)
        if old_status != citizen.profile_status:
            _notify_citizen(
                citizen,
                "Status profil actualizat",
                f"Statusul profilului tau este acum: {citizen.get_profile_status_display()}",
            )
        _notify_citizen(
            citizen,
            "Date actualizate",
            "Profilul tau a fost actualizat de operator.",
        )
        messages.success(request, "Cetatean actualizat.")
        return redirect("citizen_list")

    return render(
        request,
        "core/citizen_form.html",
        {"form": form, "formset": formset, "citizen": citizen, "self_edit": False},
    )


@user_passes_test(lambda u: u.is_staff)
def citizen_delete(request, pk):
    citizen = get_object_or_404(Citizen, pk=pk)
    muni = _user_municipality(request.user)
    if muni and citizen.municipality != muni:
        return HttpResponse(status=403)
    if request.method == "POST":
        if citizen.user:
            citizen.user.delete()
        citizen.delete()
        messages.success(request, "Cetatean sters.")
        return redirect("citizen_list")
    return render(request, "core/confirm_delete.html", {"object": citizen})


# ---- Autentificare cetatean --------------------------------------------

def citizen_login(request):
    fails = request.session.get("login_fails", 0)
    last_ts = request.session.get("last_login_attempt")
    now = timezone.now()
    wait_seconds = request.session.pop("wait_seconds", 0)
    if last_ts:
        try:
            last_dt = timezone.datetime.fromtimestamp(last_ts, tz=timezone.utc)
            elapsed = (now - last_dt).total_seconds()
            wait_seconds = max(wait_seconds, int(3 - elapsed))
        except Exception:
            wait_seconds = wait_seconds or 0

    # daca am depasit pragul si inca suntem in fereastra de asteptare, afisam countdown
    if fails >= 3 and wait_seconds > 0 and request.method != "POST":
        messages.error(request, f"Asteapta {wait_seconds} secunde inainte sa reincerci.")
        return render(request, "core/login.html", {"form": CitizenLoginForm(), "wait_seconds": wait_seconds})

    # daca am depasit pragul dar a expirat fereastra, resetam contorul
    if fails >= 3 and wait_seconds <= 0:
        request.session["login_fails"] = 0
        fails = 0
        request.session.pop("last_login_attempt", None)

    if request.user.is_authenticated and hasattr(request.user, "citizen_profile"):
        return redirect("citizen_dashboard")

    form = CitizenLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # daca inca suntem in fereastra de asteptare, nu procesam login
        if fails >= 3 and wait_seconds > 0:
            messages.error(request, f"Asteapta {wait_seconds} secunde inainte sa reincerci.")
            request.session["wait_seconds"] = wait_seconds
            return redirect("citizen_login")

        cnp = form.cleaned_data["cnp"]
        password = form.cleaned_data["password"]
        user = authenticate(request, username=cnp, password=password)
        if user:
            login(request, user)
            request.session["login_fails"] = 0
            request.session.pop("last_login_attempt", None)
            return redirect("citizen_dashboard")
        fails += 1
        request.session["login_fails"] = fails
        request.session["last_login_attempt"] = now.timestamp()
        if fails >= 3:
            messages.error(request, "Prea multe incercari. Incearca mai tarziu sau foloseste 'Am uitat parola'.")
            request.session["wait_seconds"] = 3
        else:
            messages.error(request, "CNP sau parola incorecte.")
        return redirect("citizen_login")

    return render(request, "core/login.html", {"form": form})


def citizen_logout(request):
    logout(request)
    return redirect("citizen_login")


def staff_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("admin_account")

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    form = AuthenticationForm(request, data=request.POST or None)
    if "username" in form.fields:
        form.fields["username"].widget.attrs.update({"class": "form-control"})
    if "password" in form.fields:
        form.fields["password"].widget.attrs.update({"class": "form-control"})

    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            if not user.is_staff:
                messages.error(request, "Acest cont nu are acces de administrator.")
            else:
                login(request, user)
                return redirect(next_url or "admin_account")
        else:
            messages.error(request, "Utilizator sau parola invalide.")

    return render(request, "core/staff_login.html", {"form": form, "next_url": next_url})


def superadmin_request_code(request):
    form = SuperAdminRequestCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        if email.lower() != settings.SUPER_ADMIN_EMAIL.lower():
            messages.error(request, "Email invalid pentru super admin.")
        else:
            code = f"{secrets.randbelow(10**6):06d}"
            SuperAdminCode.objects.create(code=code)
            send_mail(
                "Cod de autentificare",
                f"Codul tau este: {code}",
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            messages.success(request, "Cod trimis pe email.")
            return redirect("superadmin_verify_code")
    return render(request, "core/superadmin_request.html", {"form": form})


def superadmin_verify_code(request):
    form = SuperAdminVerifyCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        code = form.cleaned_data["code"]
        obj = SuperAdminCode.objects.filter(is_used=False).order_by("-created_at").first()
        if obj and obj.code == code:
            obj.is_used = True
            obj.save(update_fields=["is_used"])
            user, _ = User.objects.get_or_create(
                username=settings.SUPER_ADMIN_EMAIL,
                defaults={"email": settings.SUPER_ADMIN_EMAIL},
            )
            user.is_staff = True
            user.is_superuser = True
            user.set_unusable_password()
            user.save()
            login(request, user)
            messages.success(request, "Autentificat ca super admin.")
            return redirect("citizen_list")
        messages.error(request, "Cod invalid.")
    return render(request, "core/superadmin_verify.html", {"form": form})


@user_passes_test(lambda u: u.is_superuser)
def admin_invite_create(request):
    form = AdminInviteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        municipality = form.cleaned_data["municipality"]
        token = secrets.token_hex(16)
        AdminInvite.objects.create(email=email, municipality=municipality, token=token)
        link = _absolute_url(reverse("admin_invite_accept", args=[token]), request)
        send_mail(
            "Invitatie administrator primarie",
            f"Ai fost invitat ca administrator pentru {municipality.name}. Seteaza parola aici: {link}",
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        messages.success(request, "Invitatie trimisa.")
        return redirect("citizen_list")
    return render(request, "core/admin_invite_form.html", {"form": form})


def admin_invite_accept(request, token):
    invite = get_object_or_404(AdminInvite, token=token, used=False)
    form = AdminAcceptForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        password = form.cleaned_data["password1"]
        user, created = User.objects.get_or_create(
            username=invite.email,
            defaults={"email": invite.email},
        )
        user.is_staff = True
        user.set_password(password)
        user.save()
        MunicipalityAdmin.objects.update_or_create(
            user=user, defaults={"municipality": invite.municipality}
        )
        invite.used = True
        invite.used_at = timezone.now()
        invite.save(update_fields=["used", "used_at"])
        messages.success(request, "Cont creat. Te poti autentifica.")
        return redirect("citizen_login")
    return render(
        request,
        "core/admin_invite_accept.html",
        {"form": form, "municipality": invite.municipality},
    )


@user_passes_test(lambda u: u.is_superuser)
def municipality_create(request):
    form = MunicipalityForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Primarie adaugata.")
        return redirect("superadmin_overview")
    return render(request, "core/municipality_form.html", {"form": form})


@user_passes_test(lambda u: u.is_superuser)
def superadmin_send_test_email(request):
    form = SendTestEmailForm(request.POST or None)
    sent = False
    if request.method == "POST" and form.is_valid():
        to_email = form.cleaned_data["to_email"]
        try:
            send_mail(
                "Test Citizen Docs",
                "Acesta este un email de test din platforma Citizen Docs.",
                settings.DEFAULT_FROM_EMAIL,
                [to_email],
                fail_silently=False,
            )
            messages.success(request, f"Trimis catre {to_email}")
            sent = True
        except Exception as exc:
            messages.error(request, f"Eroare la trimitere: {exc}")
    return render(request, "core/send_test_email.html", {"form": form, "sent": sent})


@user_passes_test(lambda u: u.is_superuser)
def superadmin_overview(request):
    municipalities = (
        Municipality.objects.all()
        .prefetch_related("citizens", "templates")
        .order_by("name")
    )
    total_citizens = Citizen.objects.count()
    total_templates = DocumentTemplate.objects.count()
    return render(
        request,
        "core/superadmin_overview.html",
        {
            "municipalities": municipalities,
            "total_citizens": total_citizens,
            "total_templates": total_templates,
        },
    )


@user_passes_test(lambda u: u.is_superuser)
def superadmin_admins(request):
    admins_qs = MunicipalityAdmin.objects.select_related("user", "municipality").order_by(
        "municipality__name", "user__username"
    )
    summary = Municipality.objects.annotate(admin_count=models.Count("admins")).order_by("name")
    total_admins = admins_qs.count()

    if request.method == "POST":
        action = request.POST.get("action")
        admin_id = request.POST.get("admin_id")
        admin_obj = get_object_or_404(MunicipalityAdmin, pk=admin_id)
        user = admin_obj.user

        if user.is_superuser and action in {"deactivate", "delete"}:
            messages.error(request, "Nu poti dezactiva sau sterge super admin.")
            return redirect("superadmin_admins")

        if action == "deactivate":
            user.is_active = False
            user.save(update_fields=["is_active"])
            messages.success(request, f"Contul {user.username} a fost dezactivat.")
        elif action == "activate":
            user.is_active = True
            user.save(update_fields=["is_active"])
            messages.success(request, f"Contul {user.username} a fost activat.")
        elif action == "delete":
            username = user.username
            admin_obj.delete()
            user.delete()
            messages.success(request, f"Contul {username} a fost sters.")
        return redirect("superadmin_admins")

    return render(
        request,
        "core/superadmin_admins.html",
        {"admins": admins_qs, "summary": summary, "total_admins": total_admins},
    )


@user_passes_test(lambda u: u.is_superuser)
def superadmin_data_room(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete_doc":
            doc_id = request.POST.get("doc_id")
            doc = get_object_or_404(GeneratedDocument, pk=doc_id)
            if doc.file:
                doc.file.delete(save=False)
            doc.delete()
            messages.success(request, "Document sters.")
            return redirect("superadmin_data_room")
        if action == "delete_user":
            user_id = request.POST.get("user_id")
            user = get_object_or_404(User, pk=user_id)
            if user == request.user:
                messages.error(request, "Nu iti poti sterge propriul cont.")
                return redirect("superadmin_data_room")
            if user.is_superuser:
                messages.error(request, "Nu poti sterge un alt superadmin.")
                return redirect("superadmin_data_room")
            user.delete()
            messages.success(request, "Utilizator sters.")
            return redirect("superadmin_data_room")

    docs = (
        GeneratedDocument.objects.select_related("citizen", "template")
        .order_by("-created_at")[:50]
    )
    users = User.objects.order_by("-date_joined")[:50]
    total_docs = GeneratedDocument.objects.count()
    total_users = User.objects.count()
    total_citizens = Citizen.objects.count()
    media_root = settings.MEDIA_ROOT
    db_path = settings.DATABASES["default"]["NAME"]

    return render(
        request,
        "core/superadmin_data_room.html",
        {
            "docs": docs,
            "users": users,
            "total_docs": total_docs,
            "total_users": total_users,
            "total_citizens": total_citizens,
            "media_root": media_root,
            "db_path": db_path,
        },
    )


@login_required
def admin_account(request):
    muni = _user_municipality(request.user)
    if not muni:
        messages.error(request, "Nu exista o primarie asociata contului.")
        return redirect("home")

    form = MunicipalityProfileForm(
        request.POST or None, request.FILES or None, instance=muni
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Datele primariei au fost salvate.")
        return redirect("admin_account")

    citizens_count = muni.citizens.count()
    documents_count = (
        GeneratedDocument.objects.filter(citizen__municipality=muni)
        .values("id")
        .count()
    )
    recent_docs = (
        GeneratedDocument.objects.filter(citizen__municipality=muni)
        .select_related("citizen", "template")
        .order_by("-created_at")[:5]
    )

    return render(
        request,
        "core/admin_account.html",
        {
            "form": form,
            "municipality": muni,
            "citizens_count": citizens_count,
            "documents_count": documents_count,
            "recent_docs": recent_docs,
        },
    )


def _send_reset_code(user, request):
    # gaseste citizen pentru email recuperare
    citizen = getattr(user, "citizen_profile", None)
    target_email = None
    if citizen and citizen.email_recuperare:
        target_email = citizen.email_recuperare
    elif user.email:
        target_email = user.email
    if not target_email:
        return False
    code = f"{secrets.randbelow(10**6):06d}"
    expires = timezone.now() + timezone.timedelta(minutes=15)
    PasswordResetCode.objects.create(user=user, code=code, expires_at=expires)
    send_mail(
        "Cod resetare parola",
        f"Codul tau este: {code} (expira in 15 minute).",
        settings.DEFAULT_FROM_EMAIL,
        [target_email],
        fail_silently=False,
    )
    return True


def forgot_password_request(request):
    form = ForgotPasswordRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cnp = form.cleaned_data["cnp"]
        try:
            citizen = Citizen.objects.get(cnp=cnp)
            user = citizen.user
        except Citizen.DoesNotExist:
            user = None
        if user and _send_reset_code(user, request):
            messages.success(request, "Cod trimis pe email (daca exista email de recuperare).")
            return redirect("forgot_password_verify")
        messages.error(request, "Nu exista email de recuperare setat pentru acest CNP.")
    return render(request, "core/forgot_password_request.html", {"form": form})


def forgot_password_verify(request):
    form = ForgotPasswordVerifyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cnp = form.cleaned_data["cnp"]
        code = form.cleaned_data["code"]
        try:
            citizen = Citizen.objects.get(cnp=cnp)
            user = citizen.user
        except Citizen.DoesNotExist:
            user = None
        if not user:
            messages.error(request, "CNP invalid.")
            return render(request, "core/forgot_password_verify.html", {"form": form})

        reset_obj = (
            PasswordResetCode.objects.filter(user=user, code=code, used=False)
            .order_by("-created_at")
            .first()
        )
        if not reset_obj or not reset_obj.is_valid():
            messages.error(request, "Cod invalid sau expirat.")
            return render(request, "core/forgot_password_verify.html", {"form": form})

        pwd = form.cleaned_data["password1"]
        user.set_password(pwd)
        user.save()
        reset_obj.used = True
        reset_obj.save(update_fields=["used"])
        messages.success(request, "Parola a fost resetata. Te poti autentifica.")
        return redirect("citizen_login")

    return render(request, "core/forgot_password_verify.html", {"form": form})


@login_required
def citizen_send_email_code(request):
    citizen = getattr(request.user, "citizen_profile", None)
    if not citizen:
        return HttpResponse(status=403)
    email = request.POST.get("email_recuperare", "").strip()
    if not email:
        messages.error(request, "Completeaza emailul de recuperare.")
        return redirect("citizen_self_edit")
    code = f"{secrets.randbelow(10**6):06d}"
    expires = timezone.now() + timezone.timedelta(minutes=30)
    EmailVerificationCode.objects.create(
        citizen=citizen,
        email=email,
        code=code,
        expires_at=expires,
    )
    send_mail(
        "Confirmare email recuperare",
        f"Codul tau este: {code} (expira in 30 minute).",
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
    request.session[f"email_verify_requested_{citizen.id}"] = email
    messages.success(request, f"Cod trimis catre {email}. Introdu-l in pagina 'Confirma email'.")
    return redirect("citizen_self_edit")


def confirm_email(request):
    citizen = getattr(request.user, "citizen_profile", None)
    if not citizen:
        return HttpResponse(status=403)

    current_email = citizen.email_recuperare or citizen.email_recuperare_pending
    email_value = current_email
    form = ConfirmEmailForm(request.POST or None, initial={"cnp": citizen.cnp})

    if request.method == "POST":
        email_post = request.POST.get("email", "").strip()
        action_send = "send_code" in request.POST
        action_verify = "verify_code" in request.POST

        if action_send:
            if not email_post:
                messages.error(request, "Completeaza emailul.")
            else:
                code_val = f"{secrets.randbelow(10**6):06d}"
                expires = timezone.now() + timezone.timedelta(minutes=30)
                EmailVerificationCode.objects.create(
                    citizen=citizen,
                    email=email_post,
                    code=code_val,
                    expires_at=expires,
                )
                citizen.email_recuperare_pending = email_post
                citizen.save(update_fields=["email_recuperare_pending"])
                send_mail(
                    "Confirmare email recuperare",
                    f"Codul tau este: {code_val} (expira in 30 minute).",
                    settings.DEFAULT_FROM_EMAIL,
                    [email_post],
                    fail_silently=False,
                )
                messages.success(request, f"Cod trimis catre {email_post}.")
                email_value = email_post

        elif action_verify and form.is_valid():
            cnp = form.cleaned_data["cnp"]
            code = form.cleaned_data["code"]
            if cnp != citizen.cnp:
                messages.error(request, "CNP-ul nu corespunde contului.")
            else:
                evc = (
                    EmailVerificationCode.objects.filter(citizen=citizen, code=code, used=False)
                    .order_by("-created_at")
                    .first()
                )
                if not evc or not evc.is_valid():
                    messages.error(request, "Cod invalid sau expirat.")
                else:
                    citizen.email_recuperare = evc.email
                    citizen.email_recuperare_verified = True
                    citizen.email_recuperare_pending = ""
                    citizen.save(update_fields=["email_recuperare", "email_recuperare_verified", "email_recuperare_pending"])
                    evc.used = True
                    evc.save(update_fields=["used"])
                    messages.success(request, "Email validat.")
                    return redirect("citizen_dashboard")

        current_email = citizen.email_recuperare_pending or citizen.email_recuperare or email_value

    return render(request, "core/confirm_email.html", {"form": form, "current_email": current_email, "email_value": email_value})


@login_required
def chat_thread(request, citizen_id=None):
    DELETE_TOKEN = "__DELETE_REQUEST__"

    # determinam profilul cetateanului
    if request.user.is_staff:
        citizen = get_object_or_404(Citizen, id=citizen_id) if citizen_id else None
        muni = _user_municipality(request.user)
        if citizen and muni and citizen.municipality != muni:
            return HttpResponse(status=403)
    else:
        citizen = getattr(request.user, "citizen_profile", None)
        if not citizen:
            return HttpResponse(status=403)

    if citizen is None:
        return HttpResponse(status=404)

    # thread selectat
    thread_id = request.GET.get("thread")
    threads = list(citizen.chat_threads.all())
    active_thread = None
    if thread_id:
        active_thread = ChatThread.objects.filter(id=thread_id, citizen=citizen).first()
    if not active_thread:
        # creeaza un thread default daca nu exista
        if not threads:
            active_thread = ChatThread.objects.create(
                citizen=citizen,
                created_by=request.user if request.user.is_authenticated else None,
                title="Chat general",
            )
            threads = [active_thread]
        else:
            active_thread = threads[0]

    # migrare mesaje vechi fara thread -> thread activ
    Message.objects.filter(citizen=citizen, chat_thread__isnull=True).update(
        chat_thread=active_thread
    )

    msgs = (
        Message.objects.filter(citizen=citizen, chat_thread=active_thread)
        .select_related("sender")
        .order_by("-created_at")
    )
    pending_delete = msgs.filter(text=DELETE_TOKEN).exists()

    # marcheaza ca citite
    if request.user.is_staff:
        msgs.filter(sender__is_staff=False, read_by_staff=False).update(read_by_staff=True)
    else:
        msgs.filter(sender__is_staff=True, read_by_citizen=False).update(read_by_citizen=True)

    if request.method == "POST":
        # creare thread nou
        if request.POST.get("new_thread"):
            title = request.POST.get("title", "").strip() or f"Chat nou #{citizen.chat_threads.count()+1}"
            new_thread = ChatThread.objects.create(
                citizen=citizen, created_by=request.user if request.user.is_authenticated else None, title=title
            )
            return redirect(f"{request.path}?thread={new_thread.id}")

        # cerere stergere initiaza adminul: adaugam marcaj, cetateanul confirma
        if request.user.is_staff and request.POST.get("request_delete"):
            if not pending_delete:
                Message.objects.create(
                    citizen=citizen,
                    chat_thread=active_thread,
                    sender=request.user,
                    text=DELETE_TOKEN,
                )
                messages.success(request, "Solicitarea a fost trimisa cetateanului.")
            else:
                messages.info(request, "Exista deja o solicitare in asteptare pentru acest chat.")
            return redirect(request.path + f"?thread={active_thread.id}")

        # cetateanul confirma stergere: trimitem email cu istoricul si stergem
        if not request.user.is_staff and request.POST.get("confirm_delete_chat"):
            if pending_delete:
                history_msgs = Message.objects.filter(
                    citizen=citizen, chat_thread=active_thread
                ).exclude(text=DELETE_TOKEN).select_related("sender").order_by("created_at")
                history_plain = []
                history_html_parts = [
                    "<h3>Copie conversatie chat</h3>",
                    "<div style='font-family:Arial,sans-serif;font-size:14px;'>",
                ]
                for m in history_msgs:
                    who = "Admin" if m.sender and m.sender.is_staff else "Cetatean"
                    when = timezone.localtime(m.created_at).strftime("%Y-%m-%d %H:%M")
                    text = m.text or ""
                    history_plain.append(f"[{when}] {who}: {text}")
                    history_html_parts.append(
                        f"<div style='margin-bottom:8px;'><strong>{who}</strong> "
                        f"<span style='color:#6c757d;'>{when}</span><br>"
                        f"{text.replace(chr(10), '<br>')}</div>"
                    )
                    if m.attachment:
                        history_plain.append(f"  Attachment: {m.attachment.url}")
                        history_html_parts.append(
                            f"<div style='margin:4px 0 8px;'><a href='{m.attachment.url}'>Attachment</a></div>"
                        )
                history_html_parts.append("</div>")
                history_text = "\n".join(history_plain) if history_plain else "Conversatie goala."
                history_html = "".join(history_html_parts) if history_plain else "<p>Conversatie goala.</p>"
                target_email = citizen.email_recuperare or (citizen.user.email if citizen.user else None)
                if target_email:
                    try:
                        send_mail(
                            "Copie conversatie chat",
                            history_text,
                            settings.DEFAULT_FROM_EMAIL,
                            [target_email],
                            fail_silently=False,
                            html_message=history_html,
                        )
                        messages.info(request, f"Conversatia a fost trimisa pe email la {target_email}.")
                    except Exception as exc:
                        messages.warning(
                            request,
                            f"Conversatia a fost stearsa, dar emailul nu a putut fi trimis ({exc}).",
                        )
                msgs.delete()
                active_thread.delete()  # stergem si threadul pentru a disparea din lista
                messages.success(request, "Conversatia a fost stearsa.")
                return redirect(request.path)
            else:
                messages.error(request, "Nu exista o solicitare de stergere.")
                return redirect(request.path + f"?thread={active_thread.id}")

        text = request.POST.get("text", "").strip()
        attachment = request.FILES.get("attachment")
        if text or attachment:
            Message.objects.create(
                citizen=citizen,
                chat_thread=active_thread,
                sender=request.user,
                text=text,
                attachment=attachment,
            )
            return redirect(request.path + f"?thread={active_thread.id}")

    return render(
        request,
        "core/chat_thread.html",
        {
            "citizen": citizen,
            "chat_messages": msgs.exclude(text=DELETE_TOKEN),
            "pending_delete": pending_delete,
            "threads": threads,
            "active_thread": active_thread,
        },
    )


@login_required
def citizen_dashboard(request):
    citizen = getattr(request.user, "citizen_profile", None)
    if not citizen:
        messages.error(request, "Nu exista un profil de cetatean asociat.")
        return redirect("home")

    documents = citizen.documents.order_by("-created_at")[:20]
    notifications = citizen.notifications.all()[:20]
    staff_msg_count = Message.objects.filter(
        citizen=citizen, sender__is_staff=True, read_by_citizen=False
    ).count()
    work_items = citizen.work_items.select_related("template").order_by("-created_at")[:20]
    return render(
        request,
        "core/dashboard.html",
        {
            "citizen": citizen,
            "documents": documents,
            "notifications": notifications,
            "staff_msg_count": staff_msg_count,
            "work_items": work_items,
        },
    )


@login_required
def citizen_self_edit(request):
    citizen = getattr(request.user, "citizen_profile", None)
    if not citizen:
        messages.error(request, "Nu exista un profil de cetatean asociat.")
        return redirect("home")

    initial_extra = [
        {"field_name": val.field_def.name, "field_value": val.value}
        for val in citizen.extra_values.select_related("field_def")
    ]
    form = CitizenSelfForm(request.POST or None, instance=citizen)
    formset = ExtraFieldFormSet(
        request.POST or None, prefix="extra", initial=initial_extra
    )

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        old_email = citizen.email_recuperare
        new_email = form.cleaned_data.get("email_recuperare", "")
        # verifica daca s-a cerut trimiterea codului pentru acest email
        session_key = f"email_verify_requested_{citizen.id}"
        requested_email = request.session.get(session_key)
        if new_email and new_email != requested_email:
            messages.error(request, "Apasa butonul de verificare email inainte de a salva.")
            return render(
                request,
                "core/citizen_form.html",
                {"form": form, "formset": formset, "citizen": citizen, "self_edit": True},
            )

        citizen = form.save()
        _process_extra_fields(citizen, formset)
        citizen.profile_status = "pending_validation"
        citizen.save(update_fields=["profile_status"])
        # daca email recuperare s-a schimbat, trimitem cod de confirmare
        if citizen.email_recuperare and citizen.email_recuperare != old_email:
            code = f"{secrets.randbelow(10**6):06d}"
            expires = timezone.now() + timezone.timedelta(minutes=30)
            EmailVerificationCode.objects.create(
                citizen=citizen,
                email=citizen.email_recuperare,
                code=code,
                expires_at=expires,
            )
            send_mail(
                "Confirmare email recuperare",
                f"Codul tau este: {code} (expira in 30 minute).",
                settings.DEFAULT_FROM_EMAIL,
                [citizen.email_recuperare],
                fail_silently=False,
            )
            citizen.email_recuperare_verified = False
            citizen.save(update_fields=["email_recuperare_verified"])
            # resetam flag-ul de verificare
            request.session.pop(session_key, None)
        _notify_citizen(
            citizen,
            "Date actualizate",
            "Ti-ai actualizat datele de profil.",
        )
        messages.success(request, "Profil actualizat.")
        return redirect("citizen_dashboard")

    return render(
        request,
        "core/citizen_form.html",
        {"form": form, "formset": formset, "citizen": citizen, "self_edit": True},
    )


# ---- Template-uri -------------------------------------------------------

def _available_template_fields():
    exclude_citizen = {"id", "data", "user", "created_at", "updated_at", "municipality"}
    citizen_fields = [
        {"name": f.name, "placeholder": "{{ " + f.name + " }}"}
        for f in Citizen._meta.get_fields()
        if getattr(f, "concrete", False) and f.name not in exclude_citizen
    ]
    extra_defs = ExtraFieldDefinition.objects.all()
    extra_fields = [
        {"name": d.name, "placeholder": "{{ " + d.name + " }}"} for d in extra_defs
    ]
    exclude_muni = {
        "id",
        "slug",
        "created_at",
        "templates",
        "citizens",
        "admins",
    }
    muni_fields = [
        {"name": "municipality_name", "placeholder": "{{ municipality_name }}"},
        {"name": "municipality_cif", "placeholder": "{{ municipality_cif }}"},
        {"name": "municipality_email", "placeholder": "{{ municipality_email }}"},
        {"name": "municipality_phone", "placeholder": "{{ municipality_phone }}"},
        {"name": "municipality_mayor", "placeholder": "{{ municipality_mayor }}"},
        {"name": "municipality_address", "placeholder": "{{ municipality_address }}"},
        {"name": "municipality_header_logo", "placeholder": "{{ municipality_header_logo }}"},
        {"name": "municipality_header_banner", "placeholder": "{{ municipality_header_banner }}"},
    ]
    # includem si campuri brute din model pentru completare avansata
    muni_model_fields = [
        {"name": f.name, "placeholder": "{{ " + f.name + " }}"}
        for f in Municipality._meta.get_fields()
        if getattr(f, "concrete", False) and f.name not in exclude_muni
    ]
    muni_fields.extend(muni_model_fields)
    # campuri dinamice implicite (prefill)
    default_dynamic = [
        {"name": "data", "placeholder": "{{ data }}", "label": "Data", "type": "date"},
        {"name": "ora", "placeholder": "{{ ora }}", "label": "Ora", "type": "time"},
        {"name": "data_si_ora", "placeholder": "{{ data_si_ora }}", "label": "Data si ora", "type": "datetime"},
    ]
    return citizen_fields + extra_fields + default_dynamic, muni_fields


@user_passes_test(lambda u: u.is_staff)
def template_list(request):
    muni = _user_municipality(request.user)
    templates = DocumentTemplate.objects.all()
    if muni:
        templates = templates.filter(models.Q(municipalities=muni) | models.Q(municipalities__isnull=True)).distinct()
    return render(request, "core/template_list.html", {"templates": templates})


@user_passes_test(lambda u: u.is_staff)
def template_create(request):
    form = DocumentTemplateForm(request.POST or None, user=request.user)
    citizen_fields, muni_fields = _available_template_fields()
    dyn_library = DynamicFieldLibrary.objects.all().order_by("key")
    header_logo_url = ""
    header_banner_url = ""
    user_muni = _user_municipality(request.user)
    if user_muni:
        if user_muni.header_logo:
            header_logo_url = _absolute_url(user_muni.header_logo.url)
        if user_muni.header_banner:
            header_banner_url = _absolute_url(user_muni.header_banner.url)

    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user if request.user.is_authenticated else None
        obj.dynamic_fields = form.cleaned_data.get("dynamic_fields", [])
        obj.save()
        _sync_dynamic_library(obj.dynamic_fields)
        if request.user.is_superuser:
            form.save_m2m()
        else:
            muni = _user_municipality(request.user)
            if muni:
                obj.municipalities.set([muni])
        return redirect("template_list")

    return render(
        request,
        "core/template_form.html",
        {
            "form": form,
            "fields_citizen": citizen_fields,
            "fields_muni": muni_fields,
            "tmpl": None,
            "header_logo_url": header_logo_url,
            "header_banner_url": header_banner_url,
            "dynamic_library": dyn_library,
        },
    )


def template_edit(request, slug):
    tmpl = get_object_or_404(DocumentTemplate, slug=slug)
    muni = _user_municipality(request.user)
    if muni and not (tmpl.municipalities.filter(id=muni.id).exists() or tmpl.municipalities.count() == 0):
        return HttpResponse(status=403)
    form = DocumentTemplateForm(request.POST or None, instance=tmpl, user=request.user)
    citizen_fields, muni_fields = _available_template_fields()
    dyn_library = DynamicFieldLibrary.objects.all().order_by("key")
    header_logo_url = ""
    header_banner_url = ""
    if muni:
        if muni.header_logo:
            header_logo_url = _absolute_url(muni.header_logo.url)
        if muni.header_banner:
            header_banner_url = _absolute_url(muni.header_banner.url)

    if request.method == "POST" and form.is_valid():
        tmpl = form.save(commit=False)
        tmpl.dynamic_fields = form.cleaned_data.get("dynamic_fields", [])
        tmpl.save()
        _sync_dynamic_library(tmpl.dynamic_fields)
        if request.user.is_superuser:
            form.save_m2m()
        else:
            if muni:
                tmpl.municipalities.set([muni])
        messages.success(request, "Template actualizat.")
        return redirect("template_list")

    return render(
        request,
        "core/template_form.html",
        {
            "form": form,
            "tmpl": tmpl,
            "fields_citizen": citizen_fields,
            "fields_muni": muni_fields,
            "header_logo_url": header_logo_url,
            "header_banner_url": header_banner_url,
            "dynamic_library": dyn_library,
        },
    )


def template_delete(request, slug):
    tmpl = get_object_or_404(DocumentTemplate, slug=slug)
    muni = _user_municipality(request.user)
    if muni and not (tmpl.municipalities.filter(id=muni.id).exists() or tmpl.municipalities.count() == 0):
        return HttpResponse(status=403)
    if request.method == "POST":
        tmpl.delete()
        messages.success(request, "Template sters.")
        return redirect("template_list")
    return render(request, "core/confirm_delete.html", {"object": tmpl})


@user_passes_test(lambda u: u.is_superuser)
def dynamic_field_delete(request, pk):
    field = get_object_or_404(DynamicFieldLibrary, pk=pk)
    if request.method == "POST":
        field.delete()
        return JsonResponse({"ok": True})
    return JsonResponse({"error": "Method not allowed"}, status=405)


# ---- Generare document --------------------------------------------------

@user_passes_test(lambda u: u.is_staff)
def export_citizens(request):
    muni = _user_municipality(request.user)
    qs = Citizen.objects.all()
    if muni:
        qs = qs.filter(municipality=muni)
    def row_iter():
        header = ["full_name","identifier","nume","prenume","cnp","strada","nr","localitate","judet","telefon","email_recuperare","beneficiar","emitent","tip_document","numar_document_extern","data_emitere"]
        yield ",".join(header) + "\n"
        for c in qs:
            vals = [
                c.full_name or "",
                c.identifier or "",
                c.nume or "",
                c.prenume or "",
                c.cnp or "",
                c.strada or "",
                c.nr or "",
                c.localitate or "",
                c.judet or "",
                c.telefon or "",
                c.email_recuperare or "",
                c.beneficiar or "",
                c.emitent or "",
                c.tip_document or "",
                c.numar_document_extern or "",
                c.data_emitere.isoformat() if c.data_emitere else "",
            ]
            yield ",".join([v.replace(",", " ") for v in vals]) + "\n"
    resp = StreamingHttpResponse(row_iter(), content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="citizens.csv"'
    return resp


@user_passes_test(lambda u: u.is_staff)
def import_citizens(request):
    form = ImportCitizensForm(request.POST or None, request.FILES or None, user=request.user)
    session_key = "import_citizens_data"

    # Daca suntem in pasul de confirmare (choice doar), refolosim continutul din sesiune
    if request.method == "POST" and not request.FILES and request.POST.get("choice") and request.session.get(session_key):
        cached = request.session.get(session_key)
        decoded = cached.get("csv_text", "")
        muni_id = cached.get("muni_id")
        choice = request.POST.get("choice")
        skip = choice == "skip"
        overwrite = choice == "overwrite"
        muni = _user_municipality(request.user)
        if request.user.is_superuser and muni_id:
            muni = Municipality.objects.filter(pk=muni_id).first() or muni
        reader = list(csv.DictReader(decoded.splitlines()))
        count = 0
        for row in reader:
            cnp = row.get("cnp") or None
            if cnp and Citizen.objects.filter(cnp=cnp).exists() and skip:
                continue
            date_emitere = row.get("data_emitere") or None
            if date_emitere:
                try:
                    date_emitere = timezone.datetime.fromisoformat(date_emitere).date()
                except Exception:
                    date_emitere = None
            Citizen.objects.update_or_create(
                cnp=cnp,
                defaults={
                    "full_name": row.get("full_name",""),
                    "identifier": row.get("identifier",""),
                    "nume": row.get("nume",""),
                    "prenume": row.get("prenume",""),
                    "strada": row.get("strada",""),
                    "nr": row.get("nr",""),
                    "localitate": row.get("localitate",""),
                    "judet": row.get("judet",""),
                    "telefon": row.get("telefon",""),
                    "email_recuperare": row.get("email_recuperare",""),
                    "beneficiar": row.get("beneficiar",""),
                    "emitent": row.get("emitent",""),
                    "tip_document": row.get("tip_document",""),
                    "numar_document_extern": row.get("numar_document_extern",""),
                    "data_emitere": date_emitere,
                    "municipality": muni,
                },
            )
            count += 1
        messages.success(request, f"Importat {count} cetateni.")
        request.session.pop(session_key, None)
        return redirect("citizen_list")

    if request.method == "POST" and form.is_valid():
        file = form.cleaned_data["file"]
        muni = _user_municipality(request.user)
        if request.user.is_superuser:
            muni = form.cleaned_data.get("municipality") or muni
        decoded_text = file.read().decode("utf-8")
        reader = list(csv.DictReader(decoded_text.splitlines()))
        existing_cnps = []
        for row in reader:
            cnp_val = (row.get("cnp") or "").strip()
            if cnp_val and Citizen.objects.filter(cnp=cnp_val).exists():
                existing_cnps.append(cnp_val)
        overwrite = request.POST.get("overwrite")
        skip = request.POST.get("skip")
        if existing_cnps and not overwrite and not skip:
            request.session[session_key] = {"csv_text": decoded_text, "muni_id": muni.id if muni else None}
            return render(
                request,
                "core/import_citizens_confirm.html",
                {
                    "form": form,
                    "duplicates": existing_cnps,
                    "file_name": file.name,
                },
            )

        count = 0
        for row in reader:
            cnp = row.get("cnp") or None
            if cnp and Citizen.objects.filter(cnp=cnp).exists() and skip:
                continue
            date_emitere = row.get("data_emitere") or None
            if date_emitere:
                try:
                    date_emitere = timezone.datetime.fromisoformat(date_emitere).date()
                except Exception:
                    date_emitere = None
            Citizen.objects.update_or_create(
                cnp=cnp,
                defaults={
                    "full_name": row.get("full_name",""),
                    "identifier": row.get("identifier",""),
                    "nume": row.get("nume",""),
                    "prenume": row.get("prenume",""),
                    "strada": row.get("strada",""),
                    "nr": row.get("nr",""),
                    "localitate": row.get("localitate",""),
                    "judet": row.get("judet",""),
                    "telefon": row.get("telefon",""),
                    "email_recuperare": row.get("email_recuperare",""),
                    "beneficiar": row.get("beneficiar",""),
                    "emitent": row.get("emitent",""),
                    "tip_document": row.get("tip_document",""),
                    "numar_document_extern": row.get("numar_document_extern",""),
                    "data_emitere": date_emitere,
                    "municipality": muni,
                },
            )
            count += 1
        messages.success(request, f"Importat {count} cetateni.")
        return redirect("citizen_list")
    return render(request, "core/import_citizens.html", {"form": form})


@user_passes_test(lambda u: u.is_staff)
def export_templates(request):
    muni = _user_municipality(request.user)
    qs = DocumentTemplate.objects.all()
    if muni:
        qs = qs.filter(models.Q(municipalities=muni) | models.Q(municipalities__isnull=True)).distinct()
    def row_iter():
        header = ["name","description","template_type","output_type","body_html","dynamic_fields"]
        yield ",".join(header) + "\n"
        for t in qs:
            dyn = ""
            if t.dynamic_fields:
                dyn = ";".join([
                    f"{d.get('key','')}|{d.get('label','')}|{d.get('length',10)}|{d.get('type','text')}|{d.get('options','')}"
                    for d in t.dynamic_fields
                ])
            vals = [
                t.name.replace(",", " "),
                (t.description or "").replace(",", " "),
                t.template_type,
                t.output_type,
                (t.body_html or "").replace("\\n"," ").replace(","," "),
                dyn,
            ]
            yield ",".join(vals) + "\n"
    resp = StreamingHttpResponse(row_iter(), content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="templates.csv"'
    return resp


@user_passes_test(lambda u: u.is_staff)
def import_templates(request):
    form = ImportTemplatesForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        file = form.cleaned_data["file"]
        muni = _user_municipality(request.user)
        if request.user.is_superuser:
            muni = form.cleaned_data.get("municipality") or muni
        decoded = file.read().decode("utf-8").splitlines()
        reader = csv.DictReader(decoded)
        count = 0
        for row in reader:
            name = row.get("name","")
            body = row.get("body_html","")
            dyn_raw = row.get("dynamic_fields","")
            template_type = row.get("template_type","generate") or "generate"
            dyn = []
            if dyn_raw:
                # dynamic stored as ; separated of key|label|length
                lines = dyn_raw.split(";")
                dyn = parse_dynamic_fields("\\n".join(lines))
            _sync_dynamic_library(dyn)
            tmpl, _ = DocumentTemplate.objects.update_or_create(
                name=name,
                defaults={
                    "description": row.get("description",""),
                    "output_type": row.get("output_type","pdf"),
                    "template_type": template_type,
                    "body_html": body,
                    "dynamic_fields": dyn,
                },
            )
            if muni:
                tmpl.municipalities.set([muni])
            count += 1
        messages.success(request, f"Importat {count} template-uri.")
        return redirect("template_list")
    return render(request, "core/import_templates.html", {"form": form})

def generate_select(request):
    # doar staff poate genera pentru altii
    if not request.user.is_staff:
        return redirect("citizen_request_document")

    base_muni = _user_municipality(request.user)
    selected_muni = base_muni
    municipalities = None
    if request.user.is_superuser:
        municipalities = Municipality.objects.all().order_by("name")
        selected_muni_id = request.POST.get("municipality_id") or request.GET.get("municipality_id")
        if selected_muni_id:
            selected_muni = Municipality.objects.filter(pk=selected_muni_id).first()

    citizens = Citizen.objects.all()
    if selected_muni:
        citizens = citizens.filter(municipality=selected_muni)
    templates = DocumentTemplate.objects.all()
    if selected_muni:
        templates = templates.filter(models.Q(municipalities=selected_muni) | models.Q(municipalities__isnull=True)).distinct()
    if request.method == "POST":
        citizen_id = request.POST.get("citizen_id")
        template_slug = request.POST.get("template_slug")
        target = get_object_or_404(Citizen, id=citizen_id)
        tmpl = get_object_or_404(templates, slug=template_slug)
        if request.user.is_superuser and not selected_muni:
            messages.error(request, "Selecteaza mai intai institutia.")
            return redirect("generate_select")
        if target.profile_status == "pending_validation":
            messages.error(request, "Profilul acestui cetatean asteapta validare. Nu se pot genera documente.")
            return redirect("generate_select")
        # workflow: creeaza lucrare si trimite catre primarie
        if tmpl.template_type == "workflow":
            dyn_values = _extract_dynamic_values(tmpl, request.POST)
            muni_target = selected_muni or target.municipality
            safe_ctx, _ = _build_document_context(
                target,
                tmpl,
                request=request,
                dynamic_values=dyn_values,
                override_muni_id=muni_target.id if muni_target else None,
            )
            rendered = _render_document_html(tmpl, safe_ctx)
            work_item = WorkItem.objects.create(
                citizen=target,
                template=tmpl,
                municipality=muni_target,
                created_by=request.user,
                output_type=tmpl.output_type,
                dynamic_values=dyn_values,
                rendered_html=rendered,
            )
            _notify_staff_workitem(work_item=work_item)
            messages.success(request, "Document trimis pe flux catre primarie.")
            return redirect("work_item_list")
        # daca avem deja campuri completate din preview, genereaza direct
        if request.POST.get("direct_generate") == "1":
            return generate_document(request, citizen_id, template_slug)
        url = reverse("generate_document", args=[citizen_id, template_slug])
        if request.user.is_superuser and selected_muni:
            url = f"{url}?municipality_id={selected_muni.id}"
        return redirect(url)
    return render(
        request,
        "core/generate_select.html",
        {
            "citizens": citizens,
            "templates": templates,
            "municipalities": municipalities,
            "selected_muni": selected_muni,
        },
    )


@login_required
def citizen_request_document(request):
    citizen = getattr(request.user, "citizen_profile", None)
    if not citizen:
        return redirect("home")
    if citizen.profile_status == "pending_validation":
        messages.error(request, "Profilul tau asteapta validarea administratorului. Nu poti genera documente acum.")
        return redirect("citizen_dashboard")
    templates = DocumentTemplate.objects.all()
    if citizen.municipality:
        templates = templates.filter(models.Q(municipalities=citizen.municipality) | models.Q(municipalities__isnull=True)).distinct()
    if request.method == "POST":
        template_slug = request.POST.get("template_slug")
        tmpl = get_object_or_404(templates, slug=template_slug)
        if tmpl.template_type == "workflow":
            dyn_values = _extract_dynamic_values(tmpl, request.POST)
            safe_ctx, _ = _build_document_context(
                citizen,
                tmpl,
                request=request,
                dynamic_values=dyn_values,
                override_muni_id=citizen.municipality.id if citizen.municipality else None,
            )
            rendered = _render_document_html(tmpl, safe_ctx)
            work_item = WorkItem.objects.create(
                citizen=citizen,
                template=tmpl,
                municipality=citizen.municipality,
                created_by=request.user,
                output_type=tmpl.output_type,
                dynamic_values=dyn_values,
                rendered_html=rendered,
            )
            _notify_staff_workitem(work_item)
            messages.success(request, "Cererea ta a fost trimisa pe flux catre primarie.")
            return redirect("citizen_dashboard")
        if request.POST.get("direct_generate") == "1":
            return generate_document(request, citizen.id, template_slug)
        return redirect(reverse("generate_document", args=[citizen.id, template_slug]))
    return render(
        request,
        "core/generate_select.html",
        {"citizens": [citizen], "templates": templates, "citizen_mode": True},
    )


def generate_document(request, citizen_id, template_slug):
    citizen = get_object_or_404(Citizen, id=citizen_id)
    tmpl = get_object_or_404(DocumentTemplate, slug=template_slug)
    if tmpl.template_type == "workflow":
        return HttpResponse("Acest template necesita flux de lucru, nu generare directa.", status=400)

    # restrict cetateanul sa genereze doar pentru el insusi
    if request.user.is_authenticated and not request.user.is_staff:
        prof = getattr(request.user, "citizen_profile", None)
        if not prof or prof.id != citizen.id:
            return HttpResponse(status=403)
        if citizen.profile_status == "pending_validation":
            messages.error(request, "Profilul tau asteapta validarea administratorului. Nu poti genera documente.")
            return redirect("citizen_dashboard")

    # restrict adminul de primarie la cetatenii proprii
    muni = _user_municipality(request.user)
    if muni and citizen.municipality != muni:
        return HttpResponse(status=403)

    dyn_fields = getattr(tmpl, "dynamic_fields", []) or []
    if dyn_fields:
        if request.method == "GET":
            return render(
                request,
                "core/template_fill.html",
                {
                    "dynamic_fields": dyn_fields,
                    "citizen": citizen,
                    "template": tmpl,
                    "municipality_id": request.GET.get("municipality_id"),
                },
            )
    override_muni_id = request.POST.get("municipality_id") or request.GET.get("municipality_id")
    dynamic_values = request.POST if request.method == "POST" else None
    safe_context, _ = _build_document_context(
        citizen, tmpl, request=request, dynamic_values=dynamic_values, override_muni_id=override_muni_id
    )
    html_content = _render_document_html(tmpl, safe_context)

    saved, payload = _store_generated_document(tmpl, citizen, html_content, notify=True)
    if not saved:
        return HttpResponse("Eroare la generarea documentului", status=500)
    if tmpl.output_type == "pdf":
        response = HttpResponse(payload, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{tmpl.slug}.pdf"'
        return response
    if tmpl.output_type == "word":
        response = HttpResponse(payload, content_type="application/msword")
        response["Content-Disposition"] = f'attachment; filename="{tmpl.slug}.doc"'
        return response
    return HttpResponse("Tip document necunoscut.", status=400)

@login_required
def document_preview(request, doc_id):
    doc = get_object_or_404(GeneratedDocument, id=doc_id)
    # permisiuni
    if request.user.is_staff:
        muni = _user_municipality(request.user)
        if muni and doc.citizen.municipality != muni:
            return HttpResponse(status=403)
    else:
        citizen = getattr(request.user, "citizen_profile", None)
        if not citizen or citizen.id != doc.citizen_id:
            return HttpResponse(status=403)
    if not doc.file:
        return HttpResponse("Fisier indisponibil", status=404)
    doc.file.open("rb")
    data = doc.file.read()
    doc.file.close()
    content_type = "application/pdf" if doc.output_type == "pdf" else "application/msword"
    ext = "pdf" if doc.output_type == "pdf" else "doc"
    resp = HttpResponse(data, content_type=content_type)
    resp["Content-Disposition"] = f'inline; filename="{doc.template.slug}.{ext}"'
    return resp


@user_passes_test(lambda u: u.is_staff)
def work_item_list(request):
    muni = _user_municipality(request.user)
    qs = WorkItem.objects.select_related("citizen", "template", "municipality")
    if muni:
        qs = qs.filter(municipality=muni)
    status_f = request.GET.get("status", "").strip()
    if status_f:
        qs = qs.filter(status=status_f)
    items = qs.order_by("-created_at")
    return render(
        request,
        "core/work_item_list.html",
        {
            "items": items,
            "status_f": status_f,
            "status_choices": WorkItem.STATUS_CHOICES,
        },
    )


@user_passes_test(lambda u: u.is_staff)
def work_item_detail(request, pk):
    work = get_object_or_404(
        WorkItem.objects.select_related("citizen", "template", "municipality"), pk=pk
    )
    muni = _user_municipality(request.user)
    if muni and work.municipality and work.municipality != muni:
        return HttpResponse(status=403)

    tmpl = work.template
    citizen = work.citizen
    dyn_fields_raw = tmpl.dynamic_fields or []
    signature_data = work.signature or {}
    dyn_values = work.dynamic_values or {}
    signature_image_url = _absolute_url(work.signature_image.url, request=request) if work.signature_image else ""
    is_readonly = work.status == "completed"

    # marcheaza notificarile staff ca citite
    StaffNotification.objects.filter(user=request.user, work_item=work, is_read=False).update(is_read=True)

    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "delete":
            if work.status == "completed":
                messages.error(request, "Nu poti sterge un document finalizat.")
            else:
                work.delete()
                messages.success(request, "Lucrare stearsa.")
                return redirect("work_item_list")
        if is_readonly:
            messages.error(request, "Documentul este finalizat si nu mai poate fi editat.")
            return redirect("work_item_detail", pk=work.pk)
        dyn_values = _extract_dynamic_values(tmpl, request.POST)
        signature_data = {
            "text": request.POST.get("signature_text", "").strip() or signature_data.get("text", ""),
            "top": request.POST.get("signature_top", signature_data.get("top", 70)),
            "left": request.POST.get("signature_left", signature_data.get("left", 60)),
            "width": request.POST.get("signature_width", signature_data.get("width", 25)),
            "height": request.POST.get("signature_height", signature_data.get("height", 8)),
            "page": request.POST.get("signature_page", signature_data.get("page", 1)),
        }
        new_sig_image = request.FILES.get("signature_image")
        if new_sig_image:
            work.signature_image = new_sig_image
            work.save(update_fields=["signature_image"])
        if work.signature_image:
            signature_image_url = _absolute_url(work.signature_image.url, request=request)
            signature_data["image_url"] = signature_image_url
        safe_ctx, dyn_prepared = _build_document_context(
            citizen,
            tmpl,
            request=request,
            dynamic_values=dyn_values,
            override_muni_id=work.municipality_id,
            force_override=True,
        )
        base_html = _render_document_html(tmpl, safe_ctx)
        preview_html = _render_document_html(tmpl, safe_ctx, signature=signature_data, base_html_override=base_html)
        work.dynamic_values = dyn_values
        work.signature = signature_data
        work.rendered_html = base_html
        work.status = "in_progress" if work.status != "completed" else work.status
        work.save(update_fields=["dynamic_values", "signature", "rendered_html", "status", "updated_at"])

        if action == "finalize":
            saved_doc, _payload = _store_generated_document(tmpl, citizen, preview_html, notify=True)
            if saved_doc:
                work.final_document = saved_doc
                work.status = "completed"
                work.save(update_fields=["final_document", "status", "updated_at"])
                messages.success(request, f"Documentul '{tmpl.name}' pentru {citizen.full_name} a fost finalizat si trimis.")
                return redirect("work_item_list")
            else:
                messages.error(request, "Nu am putut genera documentul final.")
        else:
            messages.success(request, "Schimbarile au fost salvate.")
        # recalc preview after changes
        dyn_values = work.dynamic_values or {}
        signature_data = work.signature or {}

    safe_ctx, dyn_prepared = _build_document_context(
        citizen,
        tmpl,
        request=request,
        dynamic_values=dyn_values,
        override_muni_id=work.municipality_id,
        force_override=True,
    )
    base_html = _render_document_html(tmpl, safe_ctx)
    preview_html = _render_document_html(tmpl, safe_ctx, signature=signature_data, base_html_override=base_html)
    dyn_fields_render = []
    for item in dyn_fields_raw:
        tmp = item.copy()
        key = tmp.get("key")
        tmp["value"] = dyn_values.get(key, "")
        dyn_fields_render.append(tmp)
    return render(
        request,
        "core/work_item_detail.html",
        {
            "work": work,
            "dyn_fields": dyn_fields_render,
            "dyn_values": dyn_values,
            "signature": signature_data,
            "signature_image_url": signature_image_url,
            "preview_html": preview_html,
            "prepared_dyn_fields": dyn_prepared,
            "is_readonly": is_readonly,
        },
    )


@user_passes_test(lambda u: u.is_staff)
def work_item_delete(request, pk):
    work = get_object_or_404(
        WorkItem.objects.select_related("citizen", "municipality"), pk=pk
    )
    muni = _user_municipality(request.user)
    if muni and work.municipality and work.municipality != muni:
        return HttpResponse(status=403)
    if request.method == "POST":
        work.delete()
        messages.success(request, "Lucrare stearsa. Documentele finale raman in contul cetateanului.")
        return redirect("work_item_list")
    return redirect("work_item_list")


@login_required
@require_POST
def generate_preview(request):
    citizen_id = request.POST.get("citizen_id")
    template_slug = request.POST.get("template_slug")
    municipality_id = request.POST.get("municipality_id")
    if not citizen_id or not template_slug:
        return JsonResponse({"error": "Selecteaza cetateanul si template-ul pentru a vedea preview."}, status=400)

    citizen = get_object_or_404(Citizen, id=citizen_id)
    tmpl = get_object_or_404(DocumentTemplate, slug=template_slug)

    # permisiuni: staff doar pe cetatenii proprii; cetateanul doar pe contul lui
    if request.user.is_staff:
        muni = _user_municipality(request.user)
        if muni and citizen.municipality != muni:
            return JsonResponse({"error": "Cetateanul apartine altei institutii."}, status=403)
    else:
        prof = getattr(request.user, "citizen_profile", None)
        if not prof or prof.id != citizen.id:
            return JsonResponse({"error": "Nu ai acces la acest cetatean."}, status=403)
        if citizen.profile_status == "pending_validation":
            return JsonResponse({"error": "Profilul tau asteapta validarea administratorului."}, status=403)

    dyn_fields = getattr(tmpl, "dynamic_fields", []) or []
    dyn_values = {}
    for item in dyn_fields:
        key = item.get("key")
        if key:
            dyn_values[key] = request.POST.get(key, "")

    safe_context, prepared_dyn_fields = _build_document_context(
        citizen,
        tmpl,
        request=request,
        dynamic_values=dyn_values,
        override_muni_id=municipality_id,
    )
    html_content = _render_document_html(tmpl, safe_context)
    return JsonResponse(
        {
            "html": html_content,
            "dynamic_fields": prepared_dyn_fields,
            "template_name": tmpl.name,
            "template_type": tmpl.template_type,
            "output_type": tmpl.get_output_type_display(),
            "action_label": "Trimite pe flux" if tmpl.template_type == "workflow" else "Genereaza",
        }
    )


@user_passes_test(lambda u: u.is_staff)
def leave_dashboard(request):
    muni = _user_municipality(request.user)
    citizens_qs = Citizen.objects.filter(leave_enabled=True).order_by("full_name")
    if muni:
        citizens_qs = citizens_qs.filter(municipality=muni)
    citizens = list(citizens_qs)
    if not citizens:
        messages.error(request, "Nu exista cetateni/angajati in aceasta primarie.")
        return redirect("home")

    selected_id = request.GET.get("citizen") or request.POST.get("citizen_id") or ""
    selected_year = request.GET.get("year") or request.POST.get("year") or timezone.now().year
    try:
        selected_year = int(selected_year)
    except ValueError:
        selected_year = timezone.now().year
    selected_citizen = None
    if selected_id:
        selected_citizen = next((c for c in citizens if str(c.id) == str(selected_id)), None)
    if not selected_citizen:
        selected_citizen = citizens[0]

    # mark staff notifications as read when viewing concedii
    StaffNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_contract":
            start_str = request.POST.get("contract_start")
            allowance = request.POST.get("annual_leave_days")
            try:
                selected_citizen.contract_start = (
                    timezone.datetime.fromisoformat(start_str).date() if start_str else None
                )
            except Exception:
                messages.error(request, "Data de start a contractului nu este valida.")
                return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}")
            try:
                selected_citizen.annual_leave_days = int(allowance or 21)
            except ValueError:
                selected_citizen.annual_leave_days = 21
            selected_citizen.save(update_fields=["contract_start", "annual_leave_days"])
            messages.success(request, "Date contract actualizate.")
            return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}")

        if action == "create_request":
            start_str = request.POST.get("start_date")
            end_str = request.POST.get("end_date")
            note = request.POST.get("note", "").strip()
            try:
                start_date = timezone.datetime.fromisoformat(start_str).date()
                end_date = timezone.datetime.fromisoformat(end_str).date()
            except Exception:
                messages.error(request, "Selecteaza intervalul corect.")
                return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")
            if end_date < start_date:
                messages.error(request, "Data de sfarsit nu poate fi inainte de cea de inceput.")
                return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")
            holidays = _holiday_dates(muni)
            days_requested = _working_days_between(start_date, end_date, holidays)
            if days_requested <= 0:
                messages.error(request, "Intervalul nu contine zile lucratoare disponibile.")
                return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")
            if _overlap_exists(selected_citizen, start_date, end_date):
                messages.error(request, "Exista deja o cerere de concediu pe intervalul selectat.")
                return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")
            stats = _compute_leave_stats(selected_citizen, target_year=start_date.year)
            if days_requested > stats["available"]:
                messages.error(request, f"Solicitarea depaseste zilele disponibile ({stats['available']}).")
                return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")
            LeaveRequest.objects.create(
                citizen=selected_citizen,
                municipality=muni,
                created_by=request.user,
                start_date=start_date,
                end_date=end_date,
                days_requested=days_requested,
                note=note,
                status="pending",
            )
            _notify_citizen(
                selected_citizen,
                "Cerere concediu noua",
                f"Perioada {start_date} - {end_date}, zile: {days_requested}.",
            )
            _notify_staff_leave(
                leave_req := LeaveRequest.objects.filter(
                    citizen=selected_citizen, start_date=start_date, end_date=end_date
                ).order_by("-created_at").first(),
                "Cerere concediu noua",
                f"{selected_citizen.full_name}: {start_date} - {end_date} ({days_requested} zile)",
            )
            messages.success(request, "Cerere de concediu creata si trimisa spre aprobare.")
            return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")

        if action == "add_holiday":
            date_str = request.POST.get("holiday_date")
            label = request.POST.get("holiday_label", "").strip() or "Zi libera"
            try:
                h_date = timezone.datetime.fromisoformat(date_str).date()
            except Exception:
                messages.error(request, "Data invalida pentru ziua libera.")
                return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")
            LegalHoliday.objects.get_or_create(
                date=h_date,
                municipality=muni,
                defaults={"label": label},
            )
            messages.success(request, "Zi libera adaugata.")
            return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")
        if action == "delete_holiday":
            h_id = request.POST.get("holiday_id")
            holiday = get_object_or_404(LegalHoliday, pk=h_id)
            # global (superadmin) holidays pot fi sterse doar de superadmin
            if holiday.municipality is None and not request.user.is_superuser:
                messages.error(request, "Zilele globale pot fi sterse doar de super admin.")
                return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")
            # locale: doar in cadrul propriei primarii
            if holiday.municipality and muni and holiday.municipality != muni:
                return HttpResponse(status=403)
            holiday.delete()
            messages.success(request, "Zi libera stearsa.")
            return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")

        if action in {"approve", "reject"}:
            req_id = request.POST.get("request_id")
            leave_req = get_object_or_404(LeaveRequest, pk=req_id)
            if muni and leave_req.municipality and leave_req.municipality != muni:
                return HttpResponse(status=403)
            if leave_req.status != "pending":
                messages.info(request, "Cererea a fost deja procesata.")
                return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")
            leave_req.status = "approved" if action == "approve" else "rejected"
            if action == "reject":
                admin_note = (request.POST.get("note") or "").strip()
                if admin_note:
                    existing = leave_req.note or ""
                    leave_req.note = (existing + " " + admin_note).strip()
            leave_req.decided_by = request.user
            leave_req.decided_at = timezone.now()
            leave_req.save(update_fields=["status", "note", "decided_by", "decided_at"])
            _notify_citizen(
                leave_req.citizen,
                f"Cerere concediu {leave_req.get_status_display()}",
                f"Perioada {leave_req.start_date} - {leave_req.end_date}, zile: {leave_req.days_requested}.",
            )
            _notify_staff_leave(
                leave_req,
                f"Cerere concediu {leave_req.get_status_display()}",
                f"{leave_req.citizen.full_name}: {leave_req.start_date} - {leave_req.end_date} ({leave_req.days_requested} zile)",
            )
            messages.success(request, f"Cerere {leave_req.get_status_display().lower()}.")
            return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")

        if action == "delete_request":
            req_id = request.POST.get("request_id")
            leave_req = get_object_or_404(LeaveRequest, pk=req_id)
            if muni and leave_req.municipality and leave_req.municipality != muni:
                return HttpResponse(status=403)
            if not request.user.is_superuser and leave_req.status != "rejected":
                messages.error(request, "Doar cererile respinse pot fi sterse.")
                return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")
            leave_req.delete()
            messages.success(request, "Cerere stearsa.")
            return redirect(f"{reverse('leave_dashboard')}?citizen={selected_citizen.id}&year={selected_year}")

    stats = _compute_leave_stats(selected_citizen, target_year=selected_year)
    requests = LeaveRequest.objects.filter(citizen=selected_citizen).order_by("-created_at")[:50]
    leaves_dates = []
    for r in requests:
        cur = r.start_date
        while cur <= r.end_date:
            leaves_dates.append({"date": cur.isoformat(), "status": r.status})
            cur += timezone.timedelta(days=1)
    holidays_qs = LegalHoliday.objects.filter(models.Q(municipality__isnull=True) | models.Q(municipality=muni))
    holiday_list = [
        {"id": h.id, "date": h.date.isoformat(), "label": h.label, "is_global": h.municipality_id is None}
        for h in holidays_qs
    ]
    today = timezone.now().date()
    return render(
        request,
        "core/leave_dashboard.html",
        {
            "citizens": citizens,
            "selected_citizen": selected_citizen,
            "stats": stats,
            "requests": requests,
            "holidays": _holiday_dates(muni),
            "holiday_list": holiday_list,
            "leaves_dates": leaves_dates,
            "municipality": muni,
            "selected_year": selected_year,
            "year_options": [selected_year - 1, selected_year, selected_year + 1],
            "today": today,
        },
    )


@login_required
def leave_citizen(request):
    citizen = getattr(request.user, "citizen_profile", None)
    if not citizen:
        return HttpResponse(status=403)
    muni = citizen.municipality
    selected_year = request.GET.get("year") or request.POST.get("year") or timezone.now().year
    try:
        selected_year = int(selected_year)
    except ValueError:
        selected_year = timezone.now().year
    holidays = _holiday_dates(muni)
    stats = _compute_leave_stats(citizen, target_year=selected_year)
    # mark citizen notifications as read on concedii page
    Notification.objects.filter(citizen=citizen, is_read=False).update(is_read=True)
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "create":
            start_str = request.POST.get("start_date")
            end_str = request.POST.get("end_date")
            note = request.POST.get("note", "").strip()
            try:
                start_date = timezone.datetime.fromisoformat(start_str).date()
                end_date = timezone.datetime.fromisoformat(end_str).date()
            except Exception:
                messages.error(request, "Selecteaza intervalul corect.")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            if end_date < start_date:
                messages.error(request, "Data de sfarsit nu poate fi inainte de cea de inceput.")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            days_requested = _working_days_between(start_date, end_date, holidays)
            if days_requested <= 0:
                messages.error(request, "Intervalul nu contine zile lucratoare disponibile.")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            if _overlap_exists(citizen, start_date, end_date):
                messages.error(request, "Exista deja o cerere de concediu pe intervalul selectat.")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            stats_for_year = _compute_leave_stats(citizen, target_year=start_date.year)
            if days_requested > stats_for_year["available"]:
                messages.error(request, f"Solicitarea depaseste zilele disponibile ({stats_for_year['available']}).")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            LeaveRequest.objects.create(
                citizen=citizen,
                municipality=muni,
                created_by=request.user,
                start_date=start_date,
                end_date=end_date,
                days_requested=days_requested,
                note=note,
                status="pending",
            )
            messages.success(request, "Cerere creata si trimisa spre aprobare.")
            return redirect(f"{reverse('leave_citizen')}?year={selected_year}")

        if action == "cancel_request":
            req_id = request.POST.get("request_id")
            leave_req = get_object_or_404(LeaveRequest, pk=req_id, citizen=citizen)
            today = timezone.now().date()
            if leave_req.status == "approved" and leave_req.start_date <= today:
                messages.error(request, "Nu poti anula o cerere aprobata aflata in curs sau in trecut.")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            if leave_req.status == "rejected" and "(Anulat de utilizator)" in (leave_req.note or ""):
                messages.info(request, "Cererea este deja anulata.")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            leave_req.status = "rejected"
            note_prefix = leave_req.note or ""
            if "(Anulat de utilizator)" not in note_prefix:
                note_prefix = (note_prefix + " ").strip()
                leave_req.note = (note_prefix + "(Anulat de utilizator)").strip()
            leave_req.decided_by = request.user
            leave_req.decided_at = timezone.now()
            leave_req.save(update_fields=["status", "note", "decided_by", "decided_at"])
            _notify_staff_leave(
                leave_req,
                "Cerere concediu anulata de utilizator",
                f"{citizen.full_name}: {leave_req.start_date} - {leave_req.end_date}",
            )
            messages.success(request, "Cerere anulata.")
            return redirect(f"{reverse('leave_citizen')}?year={selected_year}")

        if action == "delete_request":
            req_id = request.POST.get("request_id")
            leave_req = get_object_or_404(LeaveRequest, pk=req_id, citizen=citizen)
            if leave_req.status != "rejected":
                messages.error(request, "Doar cererile respinse pot fi sterse.")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            leave_req.delete()
            messages.success(request, "Cerere stearsa.")
            return redirect(f"{reverse('leave_citizen')}?year={selected_year}")

        if action == "edit_request":
            req_id = request.POST.get("request_id")
            leave_req = get_object_or_404(LeaveRequest, pk=req_id, citizen=citizen)
            start_str = request.POST.get("start_date")
            end_str = request.POST.get("end_date")
            note = request.POST.get("note", leave_req.note or "").strip()
            try:
                start_date = timezone.datetime.fromisoformat(start_str).date()
                end_date = timezone.datetime.fromisoformat(end_str).date()
            except Exception:
                messages.error(request, "Selecteaza intervalul corect.")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            if end_date < start_date:
                messages.error(request, "Data de sfarsit nu poate fi inainte de cea de inceput.")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            days_requested = _working_days_between(start_date, end_date, holidays)
            if days_requested <= 0:
                messages.error(request, "Intervalul nu contine zile lucratoare disponibile.")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            if _overlap_exists(citizen, start_date, end_date, exclude_id=leave_req.id):
                messages.error(request, "Intervalul se suprapune cu alta cerere.")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            stats_for_year = _compute_leave_stats(citizen, target_year=start_date.year)
            if days_requested > stats_for_year["available"]:
                messages.error(request, f"Solicitarea depaseste zilele disponibile ({stats_for_year['available']}).")
                return redirect(f"{reverse('leave_citizen')}?year={selected_year}")
            leave_req.start_date = start_date
            leave_req.end_date = end_date
            leave_req.days_requested = days_requested
            leave_req.note = note
            leave_req.status = "pending"
            leave_req.decided_by = None
            leave_req.decided_at = None
            leave_req.save(update_fields=["start_date", "end_date", "days_requested", "note", "status", "decided_by", "decided_at"])
            messages.success(request, "Cerere actualizata si retrimisa spre aprobare.")
            return redirect(f"{reverse('leave_citizen')}?year={selected_year}")

    requests = LeaveRequest.objects.filter(citizen=citizen).order_by("-created_at")[:50]
    leaves_dates = []
    for r in requests:
        cur = r.start_date
        while cur <= r.end_date:
            leaves_dates.append({"date": cur.isoformat(), "status": r.status})
            cur += timezone.timedelta(days=1)
    holiday_list = [{"date": d.isoformat(), "label": "Zi libera"} for d in holidays]
    today = timezone.now().date()
    return render(
        request,
        "core/leave_citizen.html",
        {
            "citizen": citizen,
            "stats": stats,
            "requests": requests,
            "holiday_list": holiday_list,
            "leaves_dates": leaves_dates,
            "selected_year": selected_year,
            "year_options": [selected_year - 1, selected_year, selected_year + 1],
            "today": today,
        },
    )


# ---- Extra helpers ------------------------------------------------------

def _process_extra_fields(citizen: Citizen, formset: ExtraFieldFormSet):
    seen_ids = []
    for form in formset:
        if not form.cleaned_data or form.cleaned_data.get("DELETE"):
            continue
        name = form.cleaned_data["field_name"].strip()
        value = form.cleaned_data.get("field_value", "")
        if not name:
            continue
        field_def, _ = ExtraFieldDefinition.objects.get_or_create(
            name=name, defaults={"label": name}
        )
        val_obj, _ = ExtraFieldValue.objects.update_or_create(
            citizen=citizen, field_def=field_def, defaults={"value": value}
        )
        seen_ids.append(val_obj.field_def_id)

    ExtraFieldValue.objects.filter(citizen=citizen).exclude(
        field_def_id__in=seen_ids
    ).delete()
    citizen.refresh_data_cache()


def _notify_citizen(citizen: Citizen, title: str, message: str):
    Notification.objects.create(citizen=citizen, title=title, message=message)
    if citizen.user and citizen.user.email:
        send_mail(
            title,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [citizen.user.email],
            fail_silently=False,
        )
def _absolute_url(path: str, request=None):
    base = settings.SITE_BASE_URL
    if base:
        return f"{base}{path}"
    if request:
        return request.build_absolute_uri(path)
    return path


def _extract_dynamic_values(tmpl: DocumentTemplate, data):
    dyn_values = {}
    dyn_fields = getattr(tmpl, "dynamic_fields", []) or []
    for item in dyn_fields:
        key = item.get("key")
        if key:
            dyn_values[key] = (data.get(key) or "").strip()
    return dyn_values


def _sync_dynamic_library(dynamic_fields: list[dict]):
    for item in dynamic_fields or []:
        key = item.get("key")
        label = item.get("label") or key
        length = item.get("length", 10)
        if key:
            DynamicFieldLibrary.objects.update_or_create(
                key=key,
                defaults={
                    "label": label,
                    "length": length if isinstance(length, int) else 10,
                },
            )


def _notify_staff_workitem(work_item: WorkItem):
    if not work_item.municipality:
        return
    admins = work_item.municipality.admins.select_related("user")
    for adm in admins:
        StaffNotification.objects.create(
            user=adm.user,
            work_item=work_item,
            title="Document nou in lucru",
            message=f"{work_item.citizen.full_name} - {work_item.template.name}",
        )


def _notify_staff_leave(leave_req: LeaveRequest, title: str, message: str):
    muni = leave_req.municipality
    if not muni:
        return
    for adm in muni.admins.select_related("user"):
        StaffNotification.objects.create(
            user=adm.user,
            work_item=None,
            title=title,
            message=message,
        )
def _holiday_dates(muni: Municipality | None):
    qs = LegalHoliday.objects.filter(municipality__isnull=True)
    if muni:
        qs = LegalHoliday.objects.filter(models.Q(municipality=muni) | models.Q(municipality__isnull=True))
    return set(qs.values_list("date", flat=True))


def _overlap_exists(citizen: Citizen, start_date, end_date, exclude_id=None):
    qs = LeaveRequest.objects.filter(
        citizen=citizen,
        status__in=["pending", "approved"],
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.filter(start_date__lte=end_date, end_date__gte=start_date).exists()


def _working_days_between(start_date, end_date, holidays: set):
    days = 0
    cur = start_date
    while cur <= end_date:
        if cur.weekday() < 5 and cur not in holidays:  # 0-4 = luni-vineri
            days += 1
        cur += timezone.timedelta(days=1)
    return days


def _compute_leave_stats(citizen: Citizen, target_year: int | None = None):
    today = timezone.now().date()
    year = target_year or today.year
    year_start = timezone.datetime(year, 1, 1).date()
    year_end = timezone.datetime(year, 12, 31).date()
    contract_start = citizen.contract_start or year_start
    accrual_start = max(contract_start, year_start)
    days_in_year = (year_end - year_start).days + 1
    allowance = citizen.annual_leave_days or 21

    if year > today.year:
        accrued = allowance  # pentru anii viitori consideram alocarea intreaga
    else:
        days_employed = max(0, (today - accrual_start).days + 1) if today >= accrual_start else 0
        accrued = allowance * (days_employed / days_in_year) if days_employed else 0

    used = (
        LeaveRequest.objects.filter(
            citizen=citizen,
            status="approved",
            start_date__year=year,
        ).aggregate(total=models.Sum("days_requested"))["total"]
        or 0
    )
    available = max(0, accrued - used)
    return {
        "allowance": allowance,
        "contract_start": contract_start,
        "accrued": round(accrued, 1),
        "used": used,
        "available": round(available, 1),
        "days_in_year": days_in_year,
        "year": year,
    }


def _build_document_context(
    citizen: Citizen,
    tmpl: DocumentTemplate,
    request=None,
    dynamic_values=None,
    override_muni_id=None,
    force_override=False,
):
    context = citizen.build_data_payload(include_extra=True)
    context["full_name"] = citizen.full_name
    context["identifier"] = citizen.identifier
    # data curenta
    context["current_date"] = timezone.now().date()

    # replace lipsa cu underline
    safe_context = {}
    for k, v in context.items():
        val = v if v not in [None, "None"] else ""
        safe_context[k] = val if val else "____________________"

    muni = citizen.municipality
    # superadmin poate specifica explicit primaria (query param) ca sa foloseasca antetul corect
    if (force_override or (request and request.user.is_superuser)) and override_muni_id:
        muni = Municipality.objects.filter(pk=override_muni_id).first() or muni
    if muni:
        safe_context["municipality_name"] = muni.name
        safe_context["municipality_cif"] = muni.cif
        safe_context["municipality_email"] = muni.email
        safe_context["municipality_phone"] = muni.phone
        safe_context["municipality_mayor"] = muni.mayor_name
        safe_context["municipality_address"] = (
            f"{muni.street} {muni.number}, {muni.city}, {muni.county} {muni.postal_code}".strip()
        )
        if muni.header_logo:
            safe_context["municipality_header_logo"] = _absolute_url(
                muni.header_logo.url, request=request
            )
        if muni.header_banner:
            safe_context["municipality_header_banner"] = _absolute_url(
                muni.header_banner.url, request=request
            )

    prepared_dyn_fields = []
    dyn_fields = getattr(tmpl, "dynamic_fields", []) or []
    for item in dyn_fields:
        key = item.get("key")
        if not key:
            continue
        try:
            length = int(item.get("length", 10))
        except (TypeError, ValueError):
            length = 10
        underline = "_" * length
        val = ""
        if dynamic_values is not None:
            val = (dynamic_values.get(key) or "").strip()
        safe_context[key] = val if val else underline
        prepared_dyn_fields.append(
            {
                "key": key,
                "label": item.get("label", key),
                "length": length,
                "value": val,
                "underline": underline,
                "type": item.get("type", "text"),
                "options": item.get("options", ""),
            }
        )

    return safe_context, prepared_dyn_fields


def _render_document_html(tmpl: DocumentTemplate, safe_context: dict, signature: dict | None = None, base_html_override: str | None = None):
    if base_html_override is not None:
        # cand primim override inseamna ca body-ul este deja cu antet/continut complet, nu mai adaugam header-ul din nou
        html_content = base_html_override
        add_header = False
    else:
        # inlocuieste eventualele placeholdere scapati cu backslash
        body = tmpl.body_html.replace("\\{\\{", "{{").replace("\\}\\}", "}}")
        template = Template(body)
        html_content = template.render(Context(safe_context))
        add_header = True

    full_html = html_content
    if add_header:
        logo_src = safe_context.get("municipality_header_logo", "")
        banner_src = safe_context.get("municipality_header_banner", "")
        label_style = "height:32mm; width:52mm; object-fit:contain; display:block; margin:0 auto;"
        bar_style = "height:32mm; width:40mm; background:#444; margin:0 auto; display:block;"
        header_html = f"""
        <table style="width:100%; margin-bottom:12px; table-layout:fixed;">
          <tr style="height:32mm;">
            <td style="width:35%; text-align:center; vertical-align:middle; overflow:hidden;">
              {f'<img src="{logo_src}" alt="Sigla" style="{label_style}">' if logo_src else f'<div style="{label_style} border:1px dashed #bbb;"></div>'}
            </td>
            <td style="width:30%; text-align:center; vertical-align:middle; overflow:hidden;">
              <div style="{bar_style}"></div>
            </td>
            <td style="width:35%; text-align:center; vertical-align:middle; overflow:hidden;">
              {f'<img src="{banner_src}" alt="Banner" style="{label_style}">' if banner_src else f'<div style="{label_style} border:1px dashed #bbb;"></div>'}
            </td>
          </tr>
        </table>
        """
        full_html = header_html + html_content

    if signature and (signature.get("text") or signature.get("image_url")):
        PAGE_HEIGHT = 1123  # px, approx A4 @96dpi (aliniaza cu preview)
        PAGE_WIDTH = 794
        MM_TO_PX = 3.78
        try:
            top = float(signature.get("top", 70))
            left = float(signature.get("left", 60))
            width = float(signature.get("width", 25))
            height = float(signature.get("height", 8))
            page = int(signature.get("page", 1))
        except (TypeError, ValueError):
            top, left, width, height, page = 70.0, 60.0, 25.0, 8.0, 1
        page_offset = max(page - 1, 0) * PAGE_HEIGHT
        top_px = page_offset + (top / 100) * PAGE_HEIGHT
        left_px = (left / 100) * PAGE_WIDTH
        width_px = (width / 100) * PAGE_WIDTH
        height_px = height * MM_TO_PX
        text = signature.get("text") or "Semnatura electronica"
        image_url = signature.get("image_url", "")
        content_html = f'<div>{text}</div>'
        if image_url:
            content_html = f'<img src="{image_url}" alt="Semnatura" style="width:100%; height:100%; object-fit:contain;">'
        overlay = f"""
        <div style="
          position:absolute;
          left:{left_px}px;
          top:{top_px}px;
          width:{width_px}px;
          height:{height_px}px;
          box-sizing:border-box;
          pointer-events:none;
          color:#000;
          font-weight:600;
          text-align:center;
          display:flex;
          align-items:center;
          justify-content:center;
          z-index:10;
        ">
          {content_html}
        </div>
        """
        container_min_h = (page * PAGE_HEIGHT)
        full_html = f'<div style="position:relative; min-height:{container_min_h}px; width:{PAGE_WIDTH}px;">{full_html}{overlay}</div>'

    return full_html


def _store_generated_document(tmpl: DocumentTemplate, citizen: Citizen, html_content: str, notify=True):
    filename = f"{tmpl.slug}_{citizen.id}"
    if tmpl.output_type == "pdf":
        result = io.BytesIO()
        pisa_status = pisa.CreatePDF(html_content, dest=result)
        if pisa_status.err:
            return None, None

        saved = GeneratedDocument.objects.create(
            citizen=citizen,
            template=tmpl,
            output_type="pdf",
        )
        saved.file.save(f"{filename}.pdf", ContentFile(result.getvalue()))
        if notify:
            _notify_citizen(
                citizen,
                "Document nou",
                f"A fost generat documentul {tmpl.name}.",
            )
        return saved, result.getvalue()

    if tmpl.output_type == "word":
        saved = GeneratedDocument.objects.create(
            citizen=citizen,
            template=tmpl,
            output_type="word",
        )
        saved.file.save(f"{filename}.doc", ContentFile(html_content.encode("utf-8")))
        if notify:
            _notify_citizen(
                citizen,
                "Document nou",
                f"A fost generat documentul {tmpl.name}.",
            )
        return saved, html_content

    return None, None


# CSRF failure handler: redirect spre login cetatean
def csrf_failure_redirect(request, reason=""):
    # fortam logout si redirectionam spre login pentru a evita accesul cu sesiune invalida
    logout(request)
    messages.error(request, "Sesiunea a expirat. Te rugam sa te reconectezi.")
    return redirect("citizen_login")
