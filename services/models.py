# services/models.py
from decimal import Decimal

from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from employees.models import Specialization
from tenants.models import TenantOwnedModel

class Service(TenantOwnedModel):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    specialization = models.ForeignKey(Specialization, on_delete=models.SET_NULL, null=True, blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    # Stopped by management: gone from every picker and refused for anything
    # new; what was already booked or done under it stays as it was.
    is_active = models.BooleanField(default=True)
    # How long one session takes: what the availability engine will step by
    # (docs/15, Phase 4) and what the public page tells the customer.
    duration_minutes = models.PositiveSmallIntegerField(
        default=30, validators=[MinValueValidator(5), MaxValueValidator(600)]
    )

    class PriceDisplay(models.TextChoices):
        FIXED = "fixed", "سعر ثابت"
        STARTING_FROM = "starting_from", "يبدأ من"
        AFTER_EVALUATION = "after_evaluation", "بعد تقييم الطبيب"

    # What the public is told about the price. Advanced pricing (per pulse, per
    # area, packages) is a later, separate piece (docs/15, D12); this only says
    # whether the figure is final, a floor, or not known before the doctor sees
    # the patient.
    price_display = models.CharField(
        max_length=20, choices=PriceDisplay.choices, default=PriceDisplay.FIXED
    )
    # Some things sold are sold by the piece: pulses, millilitres, sessions,
    # units. The Owner or an Admin says which ones need a quantity; the price
    # on such a service is then a price *per unit* and a booking's total is
    # unit price × quantity (billing.pricing.apply_quantity). A service with
    # `requires_quantity` off is priced as one thing, as before.
    requires_quantity = models.BooleanField(default=False)
    # For a service sold by quantity: the real quantity is the doctor's to set,
    # inside the clinic, while the patient is in the room (pulses actually used,
    # millilitres actually given). A booking then carries an estimate — what was
    # asked for, else the smallest quantity — and what the service comes to is
    # settled by the doctor's figure.
    doctor_sets_quantity = models.BooleanField(default=False)
    #: What one unit is called on screens and receipts: "نبضة", "مل", "وحدة".
    quantity_unit = models.CharField(max_length=30, blank=True, default="")
    min_quantity = models.DecimalField(
        max_digits=8, decimal_places=2, default=1, validators=[MinValueValidator(Decimal("0.01"))]
    )
    max_quantity = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_service_name_per_tenant")
        ]

    def __str__(self):
        return f"{self.name} - {self.base_price} EGP"


class BranchService(TenantOwnedModel):
    """Whether one clinic offers one service — management's switch (docs/15, D9).

    A `Service` is defined once for the group. This says *where* it is offered
    and whether it can be booked online there. It is the administrative control:
    a clinic can enable a service before any doctor is contracted for it (a
    device, a room, a non-doctor specialist), and switching it off takes it off
    the public page without touching the doctors' contracts.

    It is not enough on its own to be booked: online booking also needs a doctor
    of that clinic under contract for the service, with a valid price
    (services/catalog.py). And a contract alone never makes a clinic offer the
    service — this row must exist and be active.
    """

    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="service_offers")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="branch_offers")
    is_active = models.BooleanField(default=True)
    # Offered at the clinic but not bookable from the website (needs a phone
    # call first, say).
    online_bookable = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "branch", "service"], name="uniq_branch_service")
        ]
        indexes = [models.Index(fields=["tenant", "branch", "is_active"], name="branchservice_branch_idx")]

    def __str__(self):
        return f"{self.branch_id}:{self.service_id}"
