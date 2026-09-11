"""The API surface, in one readable list.

Mounted under `/api/`. Nothing here shadows the existing server-rendered
screens: those keep their own URLs and keep working, which is what makes the
React application replaceable rather than a cliff.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import accounts, appointments, auth, billing, clinical, core
from .views import dashboard as dashboard_views
from .views import notifications, patients
from .views.subscription import SubscriptionView
from .views.settings import ClinicSettingsView
from .views import attendance, contracts, intake, meta, owner, shifts
from .views.print_settings import PrintSettingsView
from .views import doctor_profile
from . import platform, platform_business, platform_pay, signup

router = DefaultRouter()

# Reference data
router.register("branches", core.BranchViewSet, basename="branch")
router.register("services", core.ServiceViewSet, basename="service")
router.register("employee-types", core.EmployeeTypeViewSet, basename="employeetype")
router.register("specializations", core.SpecializationViewSet, basename="specialization")
router.register("salary-types", core.SalaryTypeViewSet, basename="salarytype")
router.register("employees", core.EmployeeViewSet, basename="employee")
router.register("doctors", core.DoctorViewSet, basename="doctor")

# People
router.register("patients", patients.PatientViewSet, basename="patient")
router.register("appointments", appointments.AppointmentViewSet, basename="appointment")

# Money
router.register("payments", billing.PaymentViewSet, basename="payment")
router.register("payment-methods", billing.PaymentMethodViewSet, basename="paymentmethod")
router.register("expenses", billing.ExpenseViewSet, basename="expense")
router.register(
    "expense-categories", billing.ExpenseCategoryViewSet, basename="expensecategory"
)
router.register(
    "financial-report", billing.FinancialReportView, basename="financialreport"
)

# Clinical
router.register("visits", clinical.VisitViewSet, basename="visit")
router.register("prescriptions", clinical.PrescriptionViewSet, basename="prescription")
router.register("treatment-plans", clinical.TreatmentPlanViewSet, basename="treatmentplan")
router.register(
    "treatment-sessions", clinical.TreatmentSessionViewSet, basename="treatmentsession"
)
router.register("procedures", clinical.ProcedureViewSet, basename="procedure")
router.register("lab-results", clinical.LabResultViewSet, basename="labresult")
router.register("attachments", clinical.MedicalAttachmentViewSet, basename="attachment")
router.register("allergies", clinical.AllergyViewSet, basename="allergy")
router.register("intakes", intake.PatientIntakeViewSet, basename="intake")
router.register("attendance", attendance.AttendanceViewSet, basename="attendance")
router.register("shifts", shifts.CashShiftViewSet, basename="shift")
router.register("doctor-rates", contracts.DoctorServiceRateViewSet, basename="doctorrate")
router.register("commissions", contracts.DoctorCommissionViewSet, basename="commission")

# Administration
router.register("staff", accounts.StaffUserViewSet, basename="staff")
router.register("roles", accounts.ClinicRoleViewSet, basename="role")

# Personal
router.register("notifications", notifications.NotificationViewSet, basename="notification")

app_name = "api"

urlpatterns = [
    path("auth/session/", auth.SessionView.as_view(), name="session"),
    path("auth/login/", auth.LoginView.as_view(), name="login"),
    path("auth/two-factor/", auth.TwoFactorView.as_view(), name="two-factor"),
    path("auth/logout/", auth.LogoutView.as_view(), name="logout"),
    path("auth/password/", auth.PasswordChangeView.as_view(), name="password-change"),
    path("auth/branch/", auth.ActiveBranchView.as_view(), name="active-branch"),
    path("branches/<uuid:uuid>/print-settings/", PrintSettingsView.as_view(), name="print-settings"),
    path("me/doctor-profile/", doctor_profile.MyDoctorProfileView.as_view(), name="my-doctor-profile"),
    path("doctor-profiles/", doctor_profile.DoctorProfileListView.as_view(), name="doctor-profiles"),
    path(
        "doctor-profiles/<uuid:uuid>/approve/",
        doctor_profile.DoctorProfileDecisionView.as_view(decision="approve"),
        name="doctor-profile-approve",
    ),
    path(
        "doctor-profiles/<uuid:uuid>/reject/",
        doctor_profile.DoctorProfileDecisionView.as_view(decision="reject"),
        name="doctor-profile-reject",
    ),
    path("dashboard/", dashboard_views.DashboardView.as_view(), name="dashboard"),
    path("subscription/", SubscriptionView.as_view(), name="subscription"),
    # The group's own invoices from the platform, and paying them online.
    path("subscription/invoices/", platform_pay.OwnerInvoicesView.as_view(), name="subscription-invoices"),
    path("subscription/invoices/<int:pk>/pay/", platform_pay.OwnerInvoicePayView.as_view(), name="subscription-invoice-pay"),
    # Asking to open a clinic group (api/signup.py). Public.
    path("signup/options/", signup.SignupOptionsView.as_view(), name="signup-options"),
    path("signup/", signup.SignupView.as_view(), name="signup"),
    # Every gateway reports back here (api/platform_pay.py). Public.
    path("pay/<str:method>/callback/", platform_pay.GatewayCallbackView.as_view(), name="gateway-callback"),
    path("clinic-settings/", ClinicSettingsView.as_view(), name="clinic-settings"),
    path("meta/choices/", meta.ChoicesView.as_view(), name="meta-choices"),
    path("intake/register/", intake.IntakeRegistrationView.as_view(), name="intake-register"),
    path("intake/duplicates/", intake.DuplicateCheckView.as_view(), name="intake-duplicates"),
    path("patients/<uuid:uuid>/history/", intake.PatientHistoryView.as_view(), name="patient-history"),
    # The group owner's dashboard (accounts/roles.py: Owner only).
    path("owner/overview/", owner.OwnerOverviewView.as_view(), name="owner-overview"),
    # The patient portal: its own authentication, never a staff session.
    path("portal/<slug:slug>/", include("portal.urls")),
    # The owner portal. Gated by is_platform_staff; see api/platform.py.
    path("platform/plans/", platform.PlanListView.as_view(), name="platform-plans"),
    path("platform/overview/", platform.OverviewView.as_view(), name="platform-overview"),
    path("platform/online/", platform.OnlineView.as_view(), name="platform-online"),
    path("platform/tenants/<uuid:uuid>/people/", platform.TenantPeopleView.as_view(), name="platform-tenant-people"),
    path("platform/tenants/", platform.TenantListView.as_view(), name="platform-tenants"),
    path("platform/tenants/<uuid:uuid>/", platform.TenantDetailView.as_view(), name="platform-tenant"),
    path("platform/tenants/<uuid:uuid>/status/", platform.TenantStatusView.as_view(), name="platform-tenant-status"),
    path("platform/tenants/<uuid:uuid>/plan/", platform.TenantPlanView.as_view(), name="platform-tenant-plan"),
    # Developer portal, phase 2 (api/platform_business.py).
    path("platform/integrations/", platform_business.IntegrationListView.as_view(), name="platform-integrations"),
    path("platform/integrations/<int:pk>/", platform_business.IntegrationDetailView.as_view(), name="platform-integration"),
    path("platform/integrations/<int:pk>/test/", platform_business.IntegrationTestView.as_view(), name="platform-integration-test"),
    path("platform/tenants/<uuid:uuid>/branches/", platform_business.TenantBranchesView.as_view(), name="platform-tenant-branches"),
    path("platform/mailboxes/", platform_business.MailboxListView.as_view(), name="platform-mailboxes"),
    path("platform/billing/", platform_business.BillingListView.as_view(), name="platform-billing"),
    path("platform/billing/invoices/<int:pk>/void/", platform_business.InvoiceVoidView.as_view(), name="platform-invoice-void"),
    path("platform/tenants/<uuid:uuid>/billing/", platform_business.TenantBillingView.as_view(), name="platform-tenant-billing"),
    path("platform/tenants/<uuid:uuid>/billing/discounts/", platform_business.DiscountView.as_view(), name="platform-tenant-discounts"),
    path("platform/tenants/<uuid:uuid>/billing/invoices/", platform_business.InvoiceIssueView.as_view(), name="platform-tenant-invoices"),
    path("platform/tenants/<uuid:uuid>/billing/payments/", platform_business.ManualPaymentView.as_view(), name="platform-tenant-payments"),
    path("platform/tenants/<uuid:uuid>/billing/late/", platform_business.LateView.as_view(), name="platform-tenant-late"),
    path("platform/signups/", signup.SignupQueueView.as_view(), name="platform-signups"),
    path("platform/signups/<int:pk>/approve/", signup.SignupApproveView.as_view(), name="platform-signup-approve"),
    path("platform/signups/<int:pk>/reject/", signup.SignupRejectView.as_view(), name="platform-signup-reject"),
    path("platform/plans/manage/", platform_business.PlanManageView.as_view(), name="platform-plans-manage"),
    path("platform/plans/<int:pk>/", platform_business.PlanDetailView.as_view(), name="platform-plan"),
    path("", include(router.urls)),
]
