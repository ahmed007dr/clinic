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

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_branch_name_per_tenant"),
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_branch_code_per_tenant"),
        ]

    def __str__(self):
        return self.name
