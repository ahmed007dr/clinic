# branches/models.py
from django.db import models
from tenants.models import TenantOwnedModel

class Branch(TenantOwnedModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    address = models.TextField(blank=True, null=True)
    # 32, not 20: an international number with an extension does not fit in 20
    # ("+20 100 123 4567 x1234" is 23), and staff routinely record two numbers
    # in one field. SQLite treated the old limit as advisory, so over-long values
    # were already present and would have failed the PostgreSQL import — see
    # DATA-001 in docs/06-implementation-progress.md.
    phone = models.CharField(max_length=32, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    logo = models.ImageField(upload_to="branches/", blank=True, null=True)
    footer_text = models.CharField(max_length=200, blank=True, null=True)
    # A clinic the Owner has stopped: its staff cannot sign in (accounts.
    # backends), it takes no bookings, and it drops out of pickers and of a
    # doctor's clinics. Its records stay, for the Owner.
    is_active = models.BooleanField(default=True)

    # The printed forms' look (the intake form, prescriptions): set by the
    # clinic's Admin or the Owner. Header = logo + name + these lines; footer
    # = `footer_text`. See templates/print/_letterhead.html.
    print_header_title = models.CharField(max_length=150, blank=True, default="")
    print_header_subtitle = models.CharField(max_length=200, blank=True, default="")
    print_accent_color = models.CharField(max_length=7, blank=True, default="#0e6e63")
    print_logo_in_footer = models.BooleanField(default=False)
    intake_form_title = models.CharField(max_length=150, blank=True, default="")
    intake_form_intro = models.TextField(blank=True, default="")
    intake_consent_text = models.TextField(blank=True, default="")
    #: Which standard sections the printed intake form carries.
    intake_sections = models.JSONField(default=list, blank=True)
    #: Extra lines the clinic wants filled in by hand: ["Referred by", ...].
    intake_extra_fields = models.JSONField(default=list, blank=True)
    #: The clinic's social and contact links — {"facebook": url, "whatsapp":
    #: number, ...}; only those filled in are shown, in the printed footer and
    #: the patient portal (branches/printing.py LINK_KINDS).
    print_links = models.JSONField(default=dict, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_branch_name_per_tenant"),
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_branch_code_per_tenant"),
        ]

    def __str__(self):
        return self.name
