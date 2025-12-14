from django import forms
from django.forms import formset_factory
from ckeditor.widgets import CKEditorWidget
import re
from .models import Citizen, DocumentTemplate, Municipality


class CitizenForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Parola",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    password2 = forms.CharField(
        label="Confirmare parola",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    municipality = forms.ModelChoiceField(
        queryset=Municipality.objects.all(),
        required=False,
        label="Primarie",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Citizen
        fields = [
            "full_name",
            "identifier",
            "nume",
            "prenume",
            "cnp",
            "strada",
            "nr",
            "localitate",
            "judet",
            "telefon",
            "email_recuperare",
            "beneficiar",
            "emitent",
            "tip_document",
            "numar_document_extern",
            "data_emitere",
            "profile_status",
            "municipality",
            "leave_enabled",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "identifier": forms.TextInput(attrs={"class": "form-control"}),
            "nume": forms.TextInput(attrs={"class": "form-control"}),
            "prenume": forms.TextInput(attrs={"class": "form-control"}),
            "cnp": forms.TextInput(attrs={"class": "form-control"}),
            "strada": forms.TextInput(attrs={"class": "form-control"}),
            "nr": forms.TextInput(attrs={"class": "form-control"}),
            "localitate": forms.TextInput(attrs={"class": "form-control"}),
            "judet": forms.TextInput(attrs={"class": "form-control"}),
            "telefon": forms.TextInput(attrs={"class": "form-control"}),
            "email_recuperare": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email recuperare (optional)"}),
            "beneficiar": forms.TextInput(attrs={"class": "form-control"}),
            "emitent": forms.TextInput(attrs={"class": "form-control"}),
            "tip_document": forms.TextInput(attrs={"class": "form-control"}),
            "numar_document_extern": forms.TextInput(attrs={"class": "form-control"}),
            "data_emitere": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "profile_status": forms.Select(attrs={"class": "form-select"}),
            "municipality": forms.Select(attrs={"class": "form-select"}),
            "leave_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # doar superadmin poate selecta primaria; adminul de primarie nu o poate schimba
        if not (self.request_user and self.request_user.is_superuser):
            self.fields.pop("municipality", None)
        else:
            self.fields["municipality"].required = True
        # profil status este vizibil staff (admin/superadmin), ascuns cetatenilor
        if not (self.request_user and self.request_user.is_staff):
            self.fields.pop("profile_status", None)
        if not (self.request_user and self.request_user.is_staff):
            self.fields.pop("leave_enabled", None)

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 or p2:
            if p1 != p2:
                self.add_error("password2", "Parolele nu coincid.")
        return cleaned


class CitizenSelfForm(forms.ModelForm):
    class Meta:
        model = Citizen
        fields = [
            "full_name",
            "identifier",
            "nume",
            "prenume",
            "cnp",
            "localitate",
            "strada",
            "nr",
            "judet",
            "telefon",
            "beneficiar",
            "emitent",
            "tip_document",
            "numar_document_extern",
            "data_emitere",
            "email_recuperare",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "readonly": True}),
            "identifier": forms.TextInput(attrs={"class": "form-control", "readonly": True}),
            "nume": forms.TextInput(attrs={"class": "form-control", "readonly": True}),
            "prenume": forms.TextInput(attrs={"class": "form-control", "readonly": True}),
            "cnp": forms.TextInput(attrs={"class": "form-control", "readonly": True}),
            "localitate": forms.TextInput(attrs={"class": "form-control", "readonly": True}),
            "strada": forms.TextInput(attrs={"class": "form-control"}),
            "nr": forms.TextInput(attrs={"class": "form-control"}),
            "judet": forms.TextInput(attrs={"class": "form-control", "readonly": True}),
            "telefon": forms.TextInput(attrs={"class": "form-control"}),
            "email_recuperare": forms.EmailInput(attrs={"class": "form-control", "readonly": True}),
            "beneficiar": forms.TextInput(attrs={"class": "form-control"}),
            "emitent": forms.TextInput(attrs={"class": "form-control"}),
            "tip_document": forms.TextInput(attrs={"class": "form-control"}),
            "numar_document_extern": forms.TextInput(attrs={"class": "form-control"}),
            "data_emitere": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        # asigura ca read-only nu pot fi schimbate
        for field in ["full_name", "identifier", "nume", "prenume", "cnp", "localitate", "judet", "email_recuperare"]:
            if field in self.fields:
                cleaned[field] = getattr(self.instance, field)
        return cleaned


class ExtraFieldForm(forms.Form):
    field_name = forms.CharField(
        label="Nume câmp", widget=forms.TextInput(attrs={"class": "form-control"})
    )
    field_value = forms.CharField(
        label="Valoare", required=False, widget=forms.TextInput(attrs={"class": "form-control"})
    )


ExtraFieldFormSet = formset_factory(ExtraFieldForm, extra=0, can_delete=True)


class DocumentTemplateForm(forms.ModelForm):
    body_html = forms.CharField(widget=CKEditorWidget())
    dynamic_fields_raw = forms.CharField(
        label="Campuri dinamice (cheie|eticheta|lungime_subray pe linie)",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        required=False,
        help_text="Ex: termen|Termen de valabilitate|20|text| (tipuri: text, date, datetime, time, year, month, day, select; pentru select se pot adauga optiuni cu virgula la final)",
    )
    municipalities = forms.ModelMultipleChoiceField(
        queryset=Municipality.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Primarii vizate",
        help_text="Lasa ne-bifat pentru a fi vizibil in toate primariile",
    )

    class Meta:
        model = DocumentTemplate
        fields = ["name", "description", "template_type", "output_type", "municipalities", "body_html", "dynamic_fields_raw"]

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["municipalities"].queryset = Municipality.objects.all().order_by("name")
        if not (self.request_user and self.request_user.is_superuser):
            self.fields.pop("municipalities", None)
        if self.instance and getattr(self.instance, "dynamic_fields", None):
            lines = []
            for item in self.instance.dynamic_fields:
                key = item.get("key", "")
                label = item.get("label", "")
                length = item.get("length", 10)
                lines.append(f"{key}|{label}|{length}")
            self.fields["dynamic_fields_raw"].initial = "\n".join(lines)
        if "template_type" in self.fields:
            self.fields["template_type"].widget.attrs.update({"class": "form-select"})
        self.fields["output_type"].widget.attrs.update({"class": "form-select"})

    def clean_dynamic_fields_raw(self):
        raw = self.cleaned_data.get("dynamic_fields_raw", "")
        return raw

    def clean(self):
        cleaned = super().clean()
        # parseaza campurile dinamice
        cleaned["dynamic_fields"] = parse_dynamic_fields(cleaned.get("dynamic_fields_raw", ""))
        return cleaned


class CitizenLoginForm(forms.Form):
    cnp = forms.CharField(
        label="CNP", widget=forms.TextInput(attrs={"class": "form-control"})
    )
    password = forms.CharField(
        label="Parola", widget=forms.PasswordInput(attrs={"class": "form-control"})
    )


class AdminInviteForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    municipality = forms.ModelChoiceField(
        queryset=Municipality.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"})
    )


class AdminAcceptForm(forms.Form):
    password1 = forms.CharField(
        label="Parola",
        widget=forms.PasswordInput(attrs={"class": "form-control"})
    )
    password2 = forms.CharField(
        label="Confirmare parola",
        widget=forms.PasswordInput(attrs={"class": "form-control"})
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "Parolele nu coincid.")
        return cleaned


class MunicipalityForm(forms.ModelForm):
    class Meta:
        model = Municipality
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }


class MunicipalityProfileForm(forms.ModelForm):
    class Meta:
        model = Municipality
        fields = [
            "name",
            "street",
            "number",
            "city",
            "county",
            "postal_code",
            "cif",
            "email",
            "phone",
            "mayor_name",
            "extra_info",
            "header_logo",
            "header_banner",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "street": forms.TextInput(attrs={"class": "form-control"}),
            "number": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "county": forms.TextInput(attrs={"class": "form-control"}),
            "postal_code": forms.TextInput(attrs={"class": "form-control"}),
            "cif": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "mayor_name": forms.TextInput(attrs={"class": "form-control"}),
            "extra_info": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "header_logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "header_banner": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }


class SendTestEmailForm(forms.Form):
    to_email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))


class SuperAdminRequestCodeForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))


class SuperAdminVerifyCodeForm(forms.Form):
    code = forms.CharField(
        label="Cod de verificare",
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "one-time-code"})
    )


class ForgotPasswordRequestForm(forms.Form):
    cnp = forms.CharField(label="CNP", widget=forms.TextInput(attrs={"class": "form-control"}))


class ForgotPasswordVerifyForm(forms.Form):
    cnp = forms.CharField(label="CNP", widget=forms.TextInput(attrs={"class": "form-control"}))
    code = forms.CharField(label="Cod primit pe email", widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "one-time-code"}))
    password1 = forms.CharField(label="Parola noua", widget=forms.PasswordInput(attrs={"class": "form-control"}))
    password2 = forms.CharField(label="Confirmare parola", widget=forms.PasswordInput(attrs={"class": "form-control"}))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "Parolele nu coincid.")
        return cleaned


class ConfirmEmailForm(forms.Form):
    cnp = forms.CharField(label="CNP", widget=forms.TextInput(attrs={"class": "form-control"}))
    code = forms.CharField(label="Cod primit pe email", widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "one-time-code"}))


def parse_dynamic_fields(raw: str):
    items = []
    raw = raw.strip() if raw else ""
    if raw:
        for line in raw.splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2 and parts[0]:
                key = re.sub(r"\s+", "_", parts[0])
                label = parts[1]
                try:
                    length = int(parts[2]) if len(parts) > 2 else 10
                except ValueError:
                    length = 10
                field_type = parts[3] if len(parts) > 3 and parts[3] else "text"
                options = parts[4] if len(parts) > 4 else ""
                items.append(
                    {
                        "key": key,
                        "label": label,
                        "length": length,
                        "type": field_type,
                        "options": options,
                    }
                )
    return items


class ImportCitizensForm(forms.Form):
    file = forms.FileField(label="Fisier CSV (UTF-8)")
    municipality = forms.ModelChoiceField(
        queryset=Municipality.objects.all(),
        required=False,
        label="Primarie (doar super admin)",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if not (user and user.is_superuser):
            self.fields.pop("municipality", None)


class ImportTemplatesForm(forms.Form):
    file = forms.FileField(label="Fisier CSV template-uri (UTF-8)")
    municipality = forms.ModelChoiceField(
        queryset=Municipality.objects.all(),
        required=False,
        label="Primarie (doar super admin; altfel se ia primaria curenta)",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if not (user and user.is_superuser):
            self.fields.pop("municipality", None)
