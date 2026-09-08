# branches/models.py
from django.db import models
from tenants.models import TenantOwnedModel

class Branch(TenantOwnedModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    logo = models.ImageField(upload_to="branches/", blank=True, null=True)
    footer_text = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_branch_name_per_tenant"),
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_branch_code_per_tenant"),
        ]

    def __str__(self):
        return self.name
