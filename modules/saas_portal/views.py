from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from core.models import Citizen
from .forms import AssetForm, AssetReviewForm, AssetTypeForm
from .forms_extra import (
    AssetRightForm,
    CaseFileForm,
    HouseholdForm,
    TaxRuleSetForm,
)
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


def _user_municipality(user):
    if not user.is_authenticated:
        return None
    if hasattr(user, "municipality_admin"):
        return user.municipality_admin.municipality
    return None


def _log_event(asset: Asset, event_type: str, user, note="", payload=None):
    evt = AssetEvent.objects.create(
        asset=asset,
        event_type=event_type,
        actor=user if user and user.is_authenticated else None,
        note=note or "",
        payload=payload or {},
    )
    return evt


@login_required
def portal_home(request):
    muni = _user_municipality(request.user)
    context = {"municipality": muni}

    if request.user.is_staff:
        assets = Asset.objects.all().select_related("asset_type", "owner", "municipality")
        asset_types = AssetType.objects.all().select_related("municipality")
        if muni:
            assets = assets.filter(municipality=muni)
            asset_types = asset_types.filter(municipality=muni)

        context["stats"] = {
            "assets_total": assets.count(),
            "assets_pending": assets.filter(status="pending").count(),
            "assets_active": assets.filter(status="active").count(),
            "asset_types_total": asset_types.count(),
        }
        context["pending"] = assets.filter(status="pending")[:5]
        context["recent_events"] = AssetEvent.objects.filter(asset__in=assets).select_related(
            "asset", "actor"
        )[:10]
        context["asset_types"] = asset_types
        return render(request, "saas_portal/home_staff.html", context)

    # citizen view
    citizen = getattr(request.user, "citizen_profile", None)
    if not citizen:
        messages.error(request, "Nu exista un profil de cetatean asociat contului.")
        return redirect("home")

    assets = (
        Asset.objects.filter(owner=citizen)
        .select_related("asset_type", "municipality")
        .order_by("-created_at")
    )
    context["assets"] = assets
    context["recent_events"] = (
        AssetEvent.objects.filter(asset__in=assets).select_related("asset").order_by("-created_at")[:10]
    )
    return render(request, "saas_portal/home_citizen.html", context)


@user_passes_test(lambda u: u.is_staff)
def ra_dashboard(request):
    muni = _user_municipality(request.user)
    households = Household.objects.select_related("municipality", "head")
    assets = Asset.objects.select_related("municipality", "owner")
    if muni:
        households = households.filter(municipality=muni)
        assets = assets.filter(municipality=muni)
    # basic report: assets without household link
    no_household = assets.exclude(household_links__isnull=False).count()
    return render(
        request,
        "saas_portal/ra_dashboard.html",
        {"households": households[:50], "no_household": no_household, "municipality": muni},
    )


@user_passes_test(lambda u: u.is_staff)
def fiscal_dashboard(request):
    muni = _user_municipality(request.user)
    accounts = FiscalAccount.objects.select_related("citizen", "municipality")
    debts = DebtItem.objects.select_related("assessment", "assessment__asset")
    if muni:
        accounts = accounts.filter(municipality=muni)
        debts = debts.filter(assessment__fiscal_account__municipality=muni)
    return render(
        request,
        "saas_portal/fiscal_dashboard.html",
        {
            "accounts": accounts[:50],
            "open_debts": debts.filter(status="open")[:50],
            "municipality": muni,
        },
    )


@login_required
def asset_list(request):
    muni = _user_municipality(request.user)
    if request.user.is_staff:
        assets = Asset.objects.select_related("owner", "asset_type", "municipality")
        if muni:
            assets = assets.filter(municipality=muni)
    else:
        citizen = getattr(request.user, "citizen_profile", None)
        if not citizen:
            messages.error(request, "Nu exista profil de cetatean.")
            return redirect("home")
        assets = Asset.objects.filter(owner=citizen).select_related("asset_type", "municipality")

    status_f = request.GET.get("status", "")
    if status_f:
        assets = assets.filter(status=status_f)

    return render(
        request,
        "saas_portal/asset_list.html",
        {"assets": assets, "status_f": status_f, "municipality": muni},
    )


@login_required
def asset_submit(request):
    user = request.user
    muni = _user_municipality(user)
    citizen = getattr(user, "citizen_profile", None)

    if not user.is_staff and not citizen:
        messages.error(request, "Trebuie sa ai profil de cetatean pentru declarare.")
        return redirect("home")

    form = AssetForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        asset = form.save(commit=False)
        owner = form.cleaned_data.get("owner") if hasattr(form, "cleaned_data") else None
        if owner:
            asset.owner = owner
        if not asset.municipality:
            asset.municipality = muni or (citizen.municipality if citizen else None) or (
                asset.asset_type.municipality if asset.asset_type else None
            )
        if not asset.owner:
            asset.owner = citizen
        if not asset.municipality and asset.owner:
            asset.municipality = asset.owner.municipality
        asset.status = "pending"
        asset.declared_by = user
        asset.save()

        # upload optional doc
        doc_link = None
        file_obj = form.cleaned_data.get("attach_file")
        if file_obj:
            doc_link = Document.objects.create(
                municipality=asset.municipality,
                uploaded_by=user if user.is_authenticated else None,
                file=file_obj,
                original_name=file_obj.name,
                size=file_obj.size,
                mime_type=getattr(file_obj, "content_type", ""),
            )

        evt = _log_event(
            asset,
            "submitted",
            user,
            payload={"data": asset.extra_data},
        )
        if doc_link:
            EventDocument.objects.create(event=evt, document=doc_link)

        # create case file
        case = CaseFile.objects.create(
            municipality=asset.municipality,
            requester=asset.owner,
            case_type="declaration",
        )
        case.reg_no = f"CF-{case.id:06d}"
        case.save(update_fields=["reg_no"])
        CaseStep.objects.create(case_file=case, step_type="review", status="open", assigned_to=None)

        messages.success(request, "Bun trimis spre validare.")
        return redirect("saas_portal:asset_detail", pk=asset.pk)

    return render(
        request,
        "saas_portal/asset_form.html",
        {"form": form, "municipality": muni},
    )


@login_required
def asset_detail(request, pk):
    asset = get_object_or_404(
        Asset.objects.select_related("asset_type", "owner", "municipality"),
        pk=pk,
    )
    # citizens can only see their own assets
    if not request.user.is_staff:
        citizen = getattr(request.user, "citizen_profile", None)
        if not citizen or asset.owner_id != citizen.id:
            return redirect("citizen_dashboard")

    events = asset.events.select_related("actor").all()
    rights = asset.rights.select_related("holder").all()
    debts = DebtItem.objects.filter(assessment__asset=asset).select_related("assessment")
    household_links = asset.household_links.select_related("household").all()
    return render(
        request,
        "saas_portal/asset_detail.html",
        {
            "asset": asset,
            "events": events,
            "rights": rights,
            "debts": debts,
            "household_links": household_links,
        },
    )


@user_passes_test(lambda u: u.is_staff)
def asset_review(request, pk):
    asset = get_object_or_404(
        Asset.objects.select_related("asset_type", "owner", "municipality"),
        pk=pk,
    )
    muni = _user_municipality(request.user)
    if muni and asset.municipality != muni:
        return redirect("saas_portal:asset_detail", pk=asset.pk)

    form = AssetReviewForm(request.POST or None, instance=asset)
    right_form = AssetRightForm(request.POST or None)
    if muni and "holder" in right_form.fields:
        right_form.fields["holder"].queryset = Citizen.objects.filter(municipality=muni).order_by("full_name")
    household_form = HouseholdForm(request.POST or None, initial={"head": asset.owner})

    if request.method == "POST":
        action = request.POST.get("action", "status")
        if action == "status" and form.is_valid():
            updated = form.save(commit=False)
            updated.save()
            evt = _log_event(
                asset,
                "status_changed",
                request.user,
                note=updated.note,
                payload={"status": updated.status},
            )
            # simple projection hooks
            if updated.status == "active":
                # ensure fiscal account
                fa, _ = FiscalAccount.objects.get_or_create(
                    municipality=asset.municipality,
                    citizen=asset.owner,
                    defaults={"opened_at": timezone.now().date()},
                )
                # create minimal assessment/debt
                year = timezone.now().year
                assessment, _ = TaxAssessment.objects.get_or_create(
                    fiscal_account=fa,
                    asset=asset,
                    period_year=year,
                    defaults={
                        "tax_type": "general",
                        "base_amount": asset.area_size or 0,
                        "rate": 0,
                        "amount": 0,
                        "explanation": {"info": "Draft automat la validare"},
                        "status": "draft",
                    },
                )
                DebtItem.objects.get_or_create(
                    assessment=assessment,
                    due_date=timezone.now().date(),
                    defaults={"amount": assessment.amount, "paid_amount": 0, "status": "open"},
                )
            messages.success(request, "Status actualizat.")
            return redirect("saas_portal:asset_detail", pk=asset.pk)

        if action == "add_right" and right_form.is_valid():
            right = right_form.save(commit=False)
            right.asset = asset
            # optional doc
            file_obj = right_form.cleaned_data.get("document_file")
            if file_obj:
                doc = Document.objects.create(
                    municipality=asset.municipality,
                    uploaded_by=request.user if request.user.is_authenticated else None,
                    file=file_obj,
                    original_name=file_obj.name,
                    size=file_obj.size,
                    mime_type=getattr(file_obj, "content_type", ""),
                )
                right.document = doc
            right.save()
            _log_event(
                asset,
                "right_added",
                request.user,
                payload={"holder": right.holder_id, "type": right.right_type},
            )
            messages.success(request, "Drept adaugat.")
            return redirect("saas_portal:asset_detail", pk=asset.pk)

        if action == "household_link" and household_form.is_valid():
            code = household_form.cleaned_data.get("code")
            name = household_form.cleaned_data.get("name")
            head = household_form.cleaned_data.get("head") or asset.owner
            hh, _ = Household.objects.get_or_create(
                municipality=asset.municipality,
                code=code,
                defaults={"name": name or code, "head": head},
            )
            HouseholdAsset.objects.get_or_create(
                household=hh, asset=asset, defaults={"relation_type": "uses"}
            )
            _log_event(asset, "household_linked", request.user, payload={"household": hh.code})
            messages.success(request, "Gospodarie asociata.")
            return redirect("saas_portal:asset_detail", pk=asset.pk)

    return render(
        request,
        "saas_portal/asset_review.html",
        {"asset": asset, "form": form, "right_form": right_form, "household_form": household_form},
    )


@user_passes_test(lambda u: u.is_staff)
def asset_type_list(request):
    muni = _user_municipality(request.user)
    types = AssetType.objects.select_related("municipality")
    if muni:
        types = types.filter(municipality=muni)
    return render(
        request,
        "saas_portal/asset_type_list.html",
        {"types": types, "municipality": muni},
    )


@user_passes_test(lambda u: u.is_staff)
def asset_type_create(request):
    muni = _user_municipality(request.user)
    form = AssetTypeForm(request.POST or None, initial={"municipality": muni})
    if request.method == "POST" and form.is_valid():
        asset_type = form.save()
        messages.success(request, "Tip de bun adaugat.")
        return redirect("saas_portal:asset_type_list")
    return render(
        request,
        "saas_portal/asset_type_form.html",
        {"form": form, "municipality": muni},
    )
