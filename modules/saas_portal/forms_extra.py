from django import forms

from .models import AssetRight, CaseFile, Document, Household, TaxRuleSet


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["file", "original_name"]

    def save(self, commit=True, municipality=None, user=None):
        obj = super().save(commit=False)
        if self.cleaned_data.get("file"):
            obj.original_name = obj.original_name or self.cleaned_data["file"].name
            obj.size = self.cleaned_data["file"].size
            obj.mime_type = getattr(self.cleaned_data["file"], "content_type", "")
        if municipality:
            obj.municipality = municipality
        if user and user.is_authenticated:
            obj.uploaded_by = user
        if commit:
            obj.save()
        return obj


class AssetRightForm(forms.ModelForm):
    document_file = forms.FileField(
        label="Document drept (optional)",
        required=False,
        help_text="Contract, extras CF etc.",
    )

    class Meta:
        model = AssetRight
        fields = ["holder", "right_type", "share", "valid_from", "valid_to", "note"]
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_to": forms.DateInput(attrs={"type": "date"}),
        }


class HouseholdForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ["code", "name", "head"]


class CaseFileForm(forms.ModelForm):
    class Meta:
        model = CaseFile
        fields = ["case_type", "sla_due_date"]
        widgets = {"sla_due_date": forms.DateInput(attrs={"type": "date"})}


class TaxRuleSetForm(forms.ModelForm):
    config_text = forms.CharField(
        label="Config (JSON simplificat, cheie:valoare pe linie)",
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
    )

    class Meta:
        model = TaxRuleSet
        fields = ["name", "version", "valid_from", "valid_to", "is_active"]
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_to": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            lines = []
            for k, v in (self.instance.config or {}).items():
                lines.append(f"{k}:{v}")
            self.fields["config_text"].initial = "\n".join(lines)

    def clean_config_text(self):
        raw = self.cleaned_data.get("config_text", "")
        config = {}
        for line in raw.splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if key:
                config[key] = val
        self.cleaned_data["config"] = config
        return raw

    def save(self, commit=True, municipality=None):
        obj = super().save(commit=False)
        obj.config = self.cleaned_data.get("config", {})
        if municipality:
            obj.municipality = municipality
        if commit:
            obj.save()
        return obj
