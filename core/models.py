from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Municipality(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    # date profil primarie
    street = models.CharField(max_length=200, blank=True)
    number = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    county = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    cif = models.CharField("Cod identificare fiscala", max_length=50, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    mayor_name = models.CharField(max_length=150, blank=True)
    extra_info = models.TextField(blank=True)
    header_logo = models.ImageField(
        upload_to="municipality_headers/", null=True, blank=True
    )
    header_banner = models.ImageField(
        upload_to="municipality_headers/", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class MunicipalityAdmin(models.Model):
    municipality = models.ForeignKey(Municipality, on_delete=models.CASCADE, related_name="admins")
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="municipality_admin")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} @ {self.municipality.name}"


class Citizen(models.Model):
    STATUS_CHOICES = [
        ("updated", "Date actualizate"),
        ("pending_validation", "Se asteapta validare"),
        ("needs_update", "Necesita actualizare"),
        ("up_to_date", "Date la zi"),
    ]

    full_name = models.CharField(max_length=200)
    identifier = models.CharField(
        max_length=50,
        blank=True,
        help_text="Ex: CNP sau un cod intern",
    )
    municipality = models.ForeignKey(
        Municipality, null=True, blank=True, on_delete=models.SET_NULL, related_name="citizens"
    )

    # user-ul pentru autentificare cetatean (username = cnp)
    user = models.OneToOneField(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="citizen_profile",
    )

    # date personale
    nume = models.CharField(max_length=100, blank=True)
    prenume = models.CharField(max_length=100, blank=True)
    cnp = models.CharField(max_length=13, unique=True, null=True, blank=True)

    # adresa
    strada = models.CharField(max_length=200, blank=True)
    nr = models.CharField(max_length=20, blank=True)
    localitate = models.CharField(max_length=200, blank=True)
    judet = models.CharField(max_length=200, blank=True)

    telefon = models.CharField(max_length=50, blank=True)
    email_recuperare = models.EmailField(blank=True)
    email_recuperare_verified = models.BooleanField(default=False)
    email_recuperare_pending = models.EmailField(blank=True)
    leave_enabled = models.BooleanField(default=True)
    contract_start = models.DateField(null=True, blank=True)
    annual_leave_days = models.PositiveIntegerField(default=21)

    # document registration type
    beneficiar = models.CharField(max_length=200, blank=True)
    emitent = models.CharField(max_length=200, blank=True)
    tip_document = models.CharField(max_length=200, blank=True)
    numar_document_extern = models.CharField(max_length=200, blank=True)
    data_emitere = models.DateField(null=True, blank=True)

    # JSON automat (fallback)
    data = models.JSONField(default=dict, blank=True)

    profile_status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default="up_to_date"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name

    def build_data_payload(self, include_extra=True):
        base = {
            "full_name": self.full_name,
            "identifier": self.identifier,
            "municipality": self.municipality.name if self.municipality else "",
            "nume": self.nume,
            "prenume": self.prenume,
            "cnp": self.cnp or "",
            "strada": self.strada,
            "nr": self.nr,
            "localitate": self.localitate,
            "judet": self.judet,
            "telefon": self.telefon,
            "beneficiar": self.beneficiar,
            "emitent": self.emitent,
            "tip_document": self.tip_document,
            "numar_document_extern": self.numar_document_extern,
            "data_emitere": str(self.data_emitere) if self.data_emitere else "",
        }

        if include_extra and self.pk:
            for val in self.extra_values.select_related("field_def").all():
                base[val.field_def.name] = val.value
        return base

    def refresh_data_cache(self):
        self.data = self.build_data_payload(include_extra=True)
        super().save(update_fields=["data"])

    def save(self, *args, **kwargs):
        # generam JSON automat din campurile introduse; extra-urile se ataseaza separat
        self.data = self.build_data_payload(include_extra=False)
        super().save(*args, **kwargs)


class ExtraFieldDefinition(models.Model):
    name = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.label or self.name


class ExtraFieldValue(models.Model):
    citizen = models.ForeignKey(
        Citizen, on_delete=models.CASCADE, related_name="extra_values"
    )
    field_def = models.ForeignKey(
        ExtraFieldDefinition, on_delete=models.CASCADE, related_name="values"
    )
    value = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["citizen", "field_def"], name="unique_extra_per_citizen"
            )
        ]

    def __str__(self):
        return f"{self.citizen} - {self.field_def.name}"


class DocumentTemplate(models.Model):
    OUTPUT_CHOICES = [
        ("pdf", "PDF"),
        ("word", "Word (.doc pe baza de HTML)"),
    ]
    TEMPLATE_TYPES = [
        ("generate", "Generare imediata"),
        ("workflow", "Trimitere pe flux"),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    body_html = models.TextField()
    output_type = models.CharField(
        max_length=10, choices=OUTPUT_CHOICES, default="pdf"
    )
    template_type = models.CharField(
        max_length=20, choices=TEMPLATE_TYPES, default="generate"
    )
    # vizibilitate: global sau pe primarii selectate
    municipalities = models.ManyToManyField(
        Municipality,
        blank=True,
        related_name="templates",
        help_text="Lasa necompletat pentru a fi disponibil tuturor primariilor",
    )

    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL
    )
    dynamic_fields = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class DynamicFieldLibrary(models.Model):
    key = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=200)
    length = models.PositiveIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} ({self.label})"


class WorkItem(models.Model):
    STATUS_CHOICES = [
        ("pending", "In lucru"),
        ("in_progress", "In editare"),
        ("completed", "Finalizat"),
    ]
    citizen = models.ForeignKey(Citizen, on_delete=models.CASCADE, related_name="work_items")
    template = models.ForeignKey(DocumentTemplate, on_delete=models.CASCADE, related_name="work_items")
    municipality = models.ForeignKey(Municipality, null=True, blank=True, on_delete=models.SET_NULL, related_name="work_items")
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="work_items_created")
    output_type = models.CharField(max_length=10, choices=DocumentTemplate.OUTPUT_CHOICES, default="pdf")
    dynamic_values = models.JSONField(default=dict, blank=True)
    rendered_html = models.TextField(blank=True)
    signature = models.JSONField(default=dict, blank=True)
    signature_image = models.ImageField(upload_to="signature_images/", null=True, blank=True)
    manual_html = models.TextField(blank=True)
    final_document = models.ForeignKey("GeneratedDocument", null=True, blank=True, on_delete=models.SET_NULL, related_name="work_items")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Lucru {self.template.name} pentru {self.citizen.full_name}"


class StaffNotification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="staff_notifications")
    work_item = models.ForeignKey(WorkItem, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=150)
    message = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.user.username}"


class LegalHoliday(models.Model):
    date = models.DateField()
    label = models.CharField(max_length=150)
    municipality = models.ForeignKey(Municipality, null=True, blank=True, on_delete=models.CASCADE, related_name="legal_holidays")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["date", "municipality"], name="unique_holiday_per_muni_or_global")
        ]

    def __str__(self):
        scope = self.municipality.name if self.municipality else "Global"
        return f"{self.label} ({self.date}) - {scope}"


class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "In asteptare"),
        ("approved", "Aprobat"),
        ("rejected", "Respins"),
    ]
    citizen = models.ForeignKey(Citizen, on_delete=models.CASCADE, related_name="leave_requests")
    municipality = models.ForeignKey(Municipality, null=True, blank=True, on_delete=models.SET_NULL, related_name="leave_requests")
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="leave_created_by")
    start_date = models.DateField()
    end_date = models.DateField()
    days_requested = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    note = models.TextField(blank=True)
    decided_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="leave_decided_by")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Concediu {self.citizen.full_name} ({self.start_date} - {self.end_date})"

class GeneratedDocument(models.Model):
    citizen = models.ForeignKey(
        Citizen, on_delete=models.CASCADE, related_name="documents"
    )
    template = models.ForeignKey(DocumentTemplate, on_delete=models.CASCADE)
    file = models.FileField(upload_to="generated_docs/")
    output_type = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.template.name} pentru {self.citizen.full_name}"


class Notification(models.Model):
    citizen = models.ForeignKey(
        Citizen, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=150)
    message = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.citizen.full_name}"


class Message(models.Model):
    citizen = models.ForeignKey(
        Citizen, on_delete=models.CASCADE, related_name="messages"
    )
    chat_thread = models.ForeignKey(
        "ChatThread",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField(blank=True)
    attachment = models.FileField(upload_to="chat_attachments/", null=True, blank=True)
    read_by_staff = models.BooleanField(default=False)
    read_by_citizen = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender} -> {self.citizen.full_name}"


class ChatThread(models.Model):
    citizen = models.ForeignKey(
        Citizen, on_delete=models.CASCADE, related_name="chat_threads"
    )
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="created_threads"
    )
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or f"Chat {self.id} - {self.citizen.full_name}"


class PasswordResetCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reset_codes")
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    def is_valid(self):
        return not self.used and timezone.now() <= self.expires_at

    def __str__(self):
        return f"Reset code for {self.user.username}"


class EmailVerificationCode(models.Model):
    citizen = models.ForeignKey(Citizen, on_delete=models.CASCADE, related_name="email_codes")
    email = models.EmailField()
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    def is_valid(self):
        return not self.used and timezone.now() <= self.expires_at

    def __str__(self):
        return f"Email code for {self.citizen.full_name}"


class AdminInvite(models.Model):
    email = models.EmailField()
    municipality = models.ForeignKey(Municipality, on_delete=models.CASCADE, related_name="invites")
    token = models.CharField(max_length=64, unique=True)
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Invite {self.email} -> {self.municipality.name}"


class SuperAdminCode(models.Model):
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return f"SuperCode {self.code}"
