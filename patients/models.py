# patients/models.py
from django.db import models
from branches.models import Branch
from django.utils import timezone
from tenants.models import SerialCounter, TenantOwnedModel

class Patient(TenantOwnedModel):   


    GENDER_CHOICES = (
        ('male', 'ذكر'),
        ('female', 'أنثى'),
    )
    MARITAL_STATUS_CHOICES = (
        ('single', 'أعزب'),
        ('married', 'متزوج'),
    )

    class ReferralSource(models.TextChoices):
        """How the patient reached the group. The value is the contract;
        the words shown to people come from the frontend's dictionaries."""

        FRIEND_FAMILY = "friend_family", "Friend / family"
        EXISTING_PATIENT = "existing_patient", "Existing patient"
        DOCTOR_REFERRAL = "doctor_referral", "Doctor referral"
        ANOTHER_CLINIC = "another_clinic", "Another clinic"
        HOSPITAL = "hospital", "Hospital"
        FACEBOOK = "facebook", "Facebook"
        INSTAGRAM = "instagram", "Instagram"
        TIKTOK = "tiktok", "TikTok"
        GOOGLE = "google", "Google"
        WEBSITE = "website", "Website"
        WHATSAPP = "whatsapp", "WhatsApp"
        ADVERTISEMENT = "advertisement", "Advertisement"
        SIGNAGE = "signage", "Street / signage"
        OTHER = "other", "Other"

    class RegistrationSource(models.TextChoices):
        STAFF = "staff", "Registered by staff"
        PORTAL = "portal", "Self-registered online"


    name = models.CharField(max_length=100)
    national_id = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='female')
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, default='single')
    birth_date = models.DateField(blank=True, null=True)
    # 32 — see Branch.phone. Eight patient rows already exceeded 20 characters.
    phone1 = models.CharField(max_length=32, blank=True, null=True)
    phone2 = models.CharField(max_length=32, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    photo = models.ImageField(upload_to='patients/', blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True) 
    # --- first-visit intake (docs/13) ---------------------------------------
    whatsapp = models.CharField(max_length=32, blank=True, default="")
    governorate = models.CharField(max_length=100, blank=True, default="")
    area = models.CharField(max_length=100, blank=True, default="")
    emergency_contact_name = models.CharField(max_length=100, blank=True, default="")
    emergency_contact_phone = models.CharField(max_length=32, blank=True, default="")
    emergency_contact_relation = models.CharField(max_length=50, blank=True, default="")

    # Acquisition: how this person reached the group. Recorded once per
    # patient, not per visit, so counting patients by source never counts the
    # same person twice. Two different facts are kept apart on purpose: who
    # sent them (source + referrer) and which of our doctors was recommended
    # (`recommended_doctor`) — the doctor they end up seeing is on the intake.
    referral_source = models.CharField(
        max_length=30, choices=ReferralSource.choices, blank=True, default=""
    )
    referral_detail = models.CharField(max_length=200, blank=True, default="")
    referring_doctor_name = models.CharField(max_length=150, blank=True, default="")
    referred_by_patient = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="referrals"
    )
    recommended_doctor = models.ForeignKey(
        "employees.Employee", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="recommended_patients",
    )

    # Consent, with *when* it was given — a bare boolean cannot answer
    # "since when", which is the question that gets asked.
    consent_data_processing_at = models.DateTimeField(null=True, blank=True)
    contact_by_phone = models.BooleanField(default=True)
    contact_by_whatsapp = models.BooleanField(default=False)
    contact_by_sms = models.BooleanField(default=False)
    contact_by_email = models.BooleanField(default=False)

    registration_source = models.CharField(
        max_length=10, choices=RegistrationSource.choices, default=RegistrationSource.STAFF
    )
    # A self-registration waits here until reception confirms it, merges it
    # into an existing patient, or rejects it.
    needs_review = models.BooleanField(default=False)

    serial_number = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)  # تاريخ الإنشاء أول مرة
    updated_at = models.DateTimeField(auto_now=True)      # آخر تعديل

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "serial_number"], name="uniq_patient_serial_per_tenant")
        ]
        # Duplicate detection looks patients up by phone and national ID; the
        # group dashboard groups new patients by source and by date.
        indexes = [
            models.Index(fields=["tenant", "phone1"], name="patient_phone_idx"),
            models.Index(fields=["tenant", "national_id"], name="patient_nid_idx"),
            models.Index(fields=["tenant", "referral_source"], name="patient_referral_idx"),
            models.Index(fields=["tenant", "created_at"], name="patient_created_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.serial_number:
            self.serial_number = SerialCounter.next_serial(self.tenant_id, "patient", timezone.now().date())
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} - {self.name}"
        