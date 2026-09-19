# branches/models.py
from django.core.validators import RegexValidator
from django.db import models
from tenants.models import TenantOwnedModel

from .media import branch_upload_path, pending_upload_path

#: Colon- or hyphen-separated hex pairs — 00:1A:2B:3C:4D:5E or 00-1A-2B-3C-4D-5E.
MAC_ADDRESS = RegexValidator(
    r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$", "عنوان MAC غير صالح (مثال: 00:1A:2B:3C:4D:5E)."
)

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
    # "About the clinic" — what the patient portal shows about this branch, before
    # and after sign-in. Written by the group's Owner or this branch's Admin
    # (api/views/about.py). The address and phone above are shown too.
    # Management can leave a branch, or a specialty of it, out of the portal's
    # "About" tab without touching the clinic itself.
    about_visible = models.BooleanField(default=True)
    about_hidden_specialties = models.ManyToManyField(
        "employees.Specialization", blank=True, related_name="hidden_in_about_of"
    )
    # Online bookings for this clinic: off (the default) = a request the clinic
    # phones back to settle; on = the chosen time is confirmed at once and held
    # for the customer (docs/15, D3). The clinic's Admin or the Owner sets it.
    online_booking_confirms_at_once = models.BooleanField(default=False)
    # How far ahead of a *confirmed* booking a patient may still cancel it from
    # the portal (docs/15, Phase 6). 0 = any time before it starts. A request the
    # clinic has not confirmed can always be withdrawn.
    online_cancel_notice_hours = models.PositiveSmallIntegerField(default=24)
    map_url = models.URLField(max_length=500, blank=True, default="")
    # Where the clinic is, for "the nearest clinic to you" on the public page
    # (docs/16). Both optional: a clinic without coordinates is still found by
    # its governorate. The customer's own location is never stored.
    governorate = models.CharField(max_length=100, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    working_hours = models.TextField(blank=True, default="")
    about_text = models.TextField(blank=True, default="")

    # The public page's logo and cover (branches/media.py, docs/15 D8). Not the
    # printed letterhead's `logo` above. An Admin's upload waits in `pending_*`
    # until the Owner approves it; only `public_*` is ever shown to the public.
    public_logo = models.ImageField(upload_to=branch_upload_path, blank=True, null=True)
    public_cover = models.ImageField(upload_to=branch_upload_path, blank=True, null=True)
    pending_public_logo = models.ImageField(upload_to=pending_upload_path, blank=True, null=True)
    pending_public_cover = models.ImageField(upload_to=pending_upload_path, blank=True, null=True)
    #: "" nothing waiting, "pending" awaiting the Owner, "rejected" (with a note).
    media_status = models.CharField(
        max_length=10, blank=True, default="",
        choices=[("", "—"), ("pending", "بانتظار موافقة المالك"), ("rejected", "مرفوض")],
    )
    media_review_note = models.CharField(max_length=300, blank=True, default="")
    media_reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    media_reviewed_at = models.DateTimeField(null=True, blank=True)

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

    # The queue ticket handed to a patient who is now waiting (branches/
    # printing.py TICKET_FIELDS) and the money receipts (payment/expense).
    # Both are set by the clinic's Admin or the Owner, same as the rest of
    # this printed look.
    class PaperWidth(models.TextChoices):
        MM58 = "58mm", "58 مم (تيرمال صغير)"
        MM80 = "80mm", "80 مم (تيرمال قياسي)"
        A5 = "a5", "A5"

    #: Which of TICKET_FIELDS are shown. Empty list (a new clinic) means
    #: everything — the same "nothing chosen yet = full form" rule as the
    #: intake form, so a fresh clinic's first ticket is not blank.
    ticket_fields = models.JSONField(default=list, blank=True)
    ticket_paper_width = models.CharField(max_length=4, choices=PaperWidth.choices, default=PaperWidth.MM80)
    ticket_note = models.CharField(max_length=200, blank=True, default="")
    receipt_paper_width = models.CharField(max_length=4, choices=PaperWidth.choices, default=PaperWidth.MM80)
    receipt_note = models.CharField(max_length=200, blank=True, default="")

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_branch_name_per_tenant"),
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_branch_code_per_tenant"),
        ]

    def __str__(self):
        return self.name


class Printer(TenantOwnedModel):
    """A physical printer registered against a branch, for a clinic that has
    more than one and needs to remember which is which.

    This is an inventory record, not a routing mechanism: the browser sends
    every print job to whatever printer Windows has installed for that IP
    (docs/10-deployment-runbook.md — "Add Printer → TCP/IP Port"). The network
    fields here are reference data for whoever next touches the physical
    printer or the router, not something the application connects to itself —
    the server has no route to a clinic's local network to begin with.
    """

    class Purpose(models.TextChoices):
        TICKET = "ticket", "تذاكر الانتظار"
        PAYMENT = "payment", "إيصالات الدفع"
        EXPENSE = "expense", "إيصالات المصروفات"

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="printers")
    name = models.CharField(max_length=100)
    purpose = models.CharField(max_length=10, choices=Purpose.choices)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    ip_address = models.GenericIPAddressField(blank=True, null=True, protocol="IPv4")
    mac_address = models.CharField(max_length=17, blank=True, default="", validators=[MAC_ADDRESS])
    subnet_mask = models.GenericIPAddressField(blank=True, null=True, protocol="IPv4")
    gateway = models.GenericIPAddressField(blank=True, null=True, protocol="IPv4")
    dhcp = models.BooleanField(default=True)
    port = models.PositiveIntegerField(default=9100)
    notes = models.CharField(max_length=200, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "branch", "name"], name="uniq_printer_name_per_branch"),
            # At most one default per purpose per branch — otherwise which one
            # the reception screen offers first would be arbitrary.
            models.UniqueConstraint(
                fields=["tenant", "branch", "purpose"], condition=models.Q(is_default=True),
                name="uniq_default_printer_per_branch_purpose",
            ),
        ]
        ordering = ["branch__name", "purpose", "name"]

    def __str__(self):
        return f"{self.name} ({self.branch.name})"
