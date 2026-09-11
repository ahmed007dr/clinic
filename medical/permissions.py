"""Who may see clinical data.

Reception books appointments, registers patients and handles payments, but
never sees a diagnosis — doc/readme.md §14 keeps Reception out of clinical
work and §87 asks for least privilege over medical data.

A doctor reads only their own patients' records — those booked with, seen by
or treated by them (accounts.roles.scope_to_own_doctor; the group owner's
decision of 2026-09-11). Cover for an absent colleague goes through an Admin
reassigning the booking. Admins see their clinic; the group Owner every clinic.

The rules themselves live in `accounts/roles.py`; this module keeps the names
the clinical views have always imported.
"""

from accounts.roles import CLINICAL_ROLES, can_view_clinical  # noqa: F401
from accounts.roles import scope_queryset_to_user as scoped_to_user  # noqa: F401
