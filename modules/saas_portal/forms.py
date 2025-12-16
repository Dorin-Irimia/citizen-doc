from django import forms

from core.models import Citizen
from .models import Asset, AssetType


def _parse_key_value_lines(raw: str) -> dict:
    data = {}
    for line in raw.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        data[key] = value
    return data


class AssetTypeForm(forms.ModelForm):
    required_fields_text = forms.CharField(
        label="Campuri obligatorii (cheie:eticheta pe linie)",
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text="Exemplu: suprafata:Suprafata (ha)\nfolosinta:Categoria de folosinta",
    )

    class Meta:
        model = AssetType
        fields = ["municipality", "code", "name", "description", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # pre-populate textarea from existing JSON
        if self.instance and self.instance.pk:
            lines = []
            for item in self.instance.required_fields or []:
                key = item.get("key")
                label = item.get("label") or key
                if key:
                    lines.append(f"{key}:{label}")
            self.fields["required_fields_text"].initial = "\n".join(lines)

    def clean_required_fields_text(self):
        raw = self.cleaned_data.get("required_fields_text", "")
        parsed = []
        for key, label in _parse_key_value_lines(raw).items():
            parsed.append({"key": key, "label": label or key})
        self.cleaned_data["required_fields"] = parsed
        return raw

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.required_fields = self.cleaned_data.get("required_fields", [])
        if commit:
            obj.save()
        return obj


class AssetForm(forms.ModelForm):
    extra_data_text = forms.CharField(
        label="Detalii suplimentare (cheie:valoare pe linie)",
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
        help_text="Exemplu: parcela:123/2\ncategoria:arabil",
    )
    attach_file = forms.FileField(
        label="Document justificativ (optional)",
        required=False,
        help_text="Contract, extras CF, proces verbal etc.",
    )

    class Meta:
        model = Asset
        fields = [
            "asset_type",
            "title",
            "identifier",
            "location",
            "area_size",
            "note",
        ]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        user = getattr(self.request, "user", None)
        if user and user.is_staff:
            self.fields["owner"] = forms.ModelChoiceField(
                queryset=Citizen.objects.select_related("municipality").order_by("full_name"),
                required=False,
                help_text="Optional: selecteaza cetateanul. Pentru self-service se foloseste automat profilul utilizatorului.",
            )
        if user and hasattr(user, "municipality_admin"):
            muni = user.municipality_admin.municipality
            self.fields["asset_type"].queryset = AssetType.objects.filter(municipality=muni, is_active=True)
            if "owner" in self.fields:
                self.fields["owner"].queryset = self.fields["owner"].queryset.filter(municipality=muni)
        # surface required fields in help text if type selected
        if self.initial.get("asset_type") and hasattr(self.initial["asset_type"], "required_fields"):
            required_keys = [item.get("key") for item in self.initial["asset_type"].required_fields or [] if item.get("key")]
            if required_keys:
                self.fields["extra_data_text"].help_text += f"\nObligatoriu: {', '.join(required_keys)}"

    def clean_extra_data_text(self):
        raw = self.cleaned_data.get("extra_data_text", "")
        return raw

    def clean(self):
        cleaned = super().clean()
        parsed = _parse_key_value_lines(cleaned.get("extra_data_text", "") or "")
        cleaned["extra_data"] = parsed
        user = getattr(self.request, "user", None)
        if user and user.is_staff:
            owner = cleaned.get("owner")
            if not owner:
                self.add_error("owner", "Selecteaza proprietarul.")
        asset_type = cleaned.get("asset_type")
        # check required dynamic fields
        if asset_type and getattr(asset_type, "required_fields", None):
            missing = []
            for item in asset_type.required_fields or []:
                key = (item or {}).get("key")
                if key and not parsed.get(key):
                    missing.append(item.get("label") or key)
            if missing:
                self.add_error("extra_data_text", f"Lipsesc campurile obligatorii: {', '.join(missing)}")
        # positive area if provided
        area_size = cleaned.get("area_size")
        if area_size is not None and area_size <= 0:
            self.add_error("area_size", "Suprafata trebuie sa fie pozitiva.")
        # uniqueness for identifier within municipality
        identifier = (cleaned.get("identifier") or "").strip()
        if identifier:
            target_owner = cleaned.get("owner") or getattr(user, "citizen_profile", None)
            target_muni = None
            if target_owner:
                target_muni = target_owner.municipality
            if user and hasattr(user, "municipality_admin"):
                target_muni = user.municipality_admin.municipality
            if target_muni:
                exists = Asset.objects.filter(
                    municipality=target_muni,
                    identifier=identifier,
                )
                if self.instance and self.instance.pk:
                    exists = exists.exclude(pk=self.instance.pk)
                if exists.exists():
                    self.add_error("identifier", "Exista deja un bun cu acest identificator in primarie.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.extra_data = self.cleaned_data.get("extra_data", {})
        # set municipality from owner or asset type if absent
        if not obj.municipality:
            if obj.owner and obj.owner.municipality:
                obj.municipality = obj.owner.municipality
            elif obj.asset_type and obj.asset_type.municipality:
                obj.municipality = obj.asset_type.municipality
        if commit:
            obj.save()
        return obj


class AssetReviewForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = ["status", "note"]

    def clean_status(self):
        status = self.cleaned_data.get("status")
        if status not in ["active", "rejected", "archived"]:
            raise forms.ValidationError("Status invalid.")
        return status
