# services/models.py
from django.db import models
from django.core.validators import MinValueValidator
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

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_service_name_per_tenant")
        ]

    def __str__(self):
        return f"{self.name} - {self.base_price} EGP"
