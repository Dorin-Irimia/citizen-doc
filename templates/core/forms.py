from django import forms
from ckeditor.widgets import CKEditorWidget
from .models import Citizen, DocumentTemplate


class CitizenForm(forms.ModelForm):
    class Meta:
        model = Citizen
        fields = ["full_name", "identifier", "data_raw"]  # dacă încă folosești JSON-ul
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "identifier": forms.TextInput(attrs={"class": "form-control"}),
            "data_raw": forms.Textarea(attrs={"class": "form-control", "rows": 12}),
        }


class DocumentTemplateForm(forms.ModelForm):
    body_html = forms.CharField(widget=CKEditorWidget())

    class Meta:
        model = DocumentTemplate
        fields = ["name", "description", "body_html", "output_type"]
