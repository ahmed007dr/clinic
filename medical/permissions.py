"""Who may see clinical data.

Reception books appointments, registers patients and handles payments, but
never sees a diagnosis — doc/readme.md §14 keeps Reception out of clinical
work and §87 asks for least privilege over medical data.

Any doctor in a clinic can read any of that clinic's patients' records, which
is what makes cover, handover and second opinions possible. The group Owner
sees every clinic.

The rules themselves live in `accounts/roles.py`; this module keeps the names
the clinical views have always imported.
"""

from accounts.roles import CLINICAL_ROLES, can_view_clinical  # noqa: F401
from accounts.roles import scope_queryset_to_user as scoped_to_user  # noqa: F401
