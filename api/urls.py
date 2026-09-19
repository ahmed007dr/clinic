"""The API surface, in one readable list.

Mounted under `/api/`. Nothing here shadows the existing server-rendered
screens: those keep their own URLs and keep working, which is what makes the
React application replaceable rather than a cliff.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import accounts, appointments, auth, billing, clinical, core, printers
from .views import dashboard as dashboard_views
from .views import notifications, patients
from .views.subscription import SubscriptionView
from .views.settings import ClinicSettingsView
from .views import service_orders
from .views import about, attendance, contracts, coupons, email_log, intake, meta, owner, owner_email, shifts
from .views.print_settings import PrintSettingsView
from .views import branch_services, doctor_profile, my_report, public_media, schedules
from . import directory, platform, platform_backups, platform_business, platform_control, platform_pay, signup

router = DefaultRouter()

# Reference data
router.register("branches", core.BranchViewSet, basename="branch")
router.register("printers", printers.PrinterViewSet, basename="printer")
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
router.register("about", about.BranchAboutViewSet, basename="about")
router.register("coupons", coupons.CouponViewSet, basename="coupon")
router.register("doctor-time-off", schedules.DoctorTimeOffViewSet, basename="doctortimeoff")
router.register("branch-holidays", schedules.BranchHolidayViewSet, basename="branchholiday")
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
    path("auth/support/end/", platform_control.SupportEndView.as_view(), name="support-end"),
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
    path("my-report/email/", my_report.MyReportEmailView.as_view(), name="my-report-email"),
    path("subscription/", SubscriptionView.as_view(), name="subscription"),
    # The group's own invoices from the platform, and paying them online.
    path("subscription/invoices/", platform_pay.OwnerInvoicesView.as_view(), name="subscription-invoices"),
    path("subscription/invoices/<int:pk>/pay/", platform_pay.OwnerInvoicePayView.as_view(), name="subscription-invoice-pay"),
    # Asking to open a clinic group (api/signup.py). Public.
    # The public directory of clinic groups — the site's front door (api/directory.py).
    path("directory/", directory.DirectoryView.as_view(), name="directory"),
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
    # The email log: what was sent, to whom, and what it said.
    path("email-log/", email_log.EmailLogListView.as_view(), name="email-log"),
    path("email-log/<uuid:uuid>/", email_log.EmailLogDetailView.as_view(), name="email-log-detail"),
    path("email-log/<uuid:uuid>/resend/", email_log.EmailLogResendView.as_view(), name="email-log-resend"),
    path("platform/tenants/<uuid:uuid>/email-log/", email_log.PlatformEmailLogListView.as_view(), name="platform-email-log"),
    path("platform/tenants/<uuid:uuid>/email-log/<uuid:log_uuid>/", email_log.PlatformEmailLogDetailView.as_view(), name="platform-email-log-detail"),
    # The owner's email settings: the group's default and each clinic's own.
    path("owner/email/", owner_email.OwnerEmailView.as_view(), name="owner-email"),
    path("owner/email/apply-default/", owner_email.OwnerEmailApplyDefaultView.as_view(), name="owner-email-apply-default"),
    path("owner/email/<str:target>/", owner_email.OwnerEmailTargetView.as_view(), name="owner-email-target"),
    path("owner/email/<str:target>/test/", owner_email.OwnerEmailTestView.as_view(), name="owner-email-test"),
    # Doctors' weekly hours (docs/15, Phase 4).
    path("schedules/", schedules.SchedulesView.as_view(), name="schedules"),
    # Which services each clinic offers (docs/15, D9).
    path("branch-services/", branch_services.BranchServicesView.as_view(), name="branch-services"),
    # The public page's logo and cover, with the Owner's approval (docs/15, D8).
    # The customers' service orders, from the clinic's side (docs/16, Phase C).
    path("service-orders/", service_orders.ServiceOrderListView.as_view(), name="service-orders"),
    path("service-orders/<uuid:uuid>/", service_orders.ServiceOrderDetailView.as_view(), name="service-order-detail"),
    path("service-orders/<uuid:uuid>/approve/", service_orders.ServiceOrderApproveView.as_view(), name="service-order-approve"),
    path("service-orders/<uuid:uuid>/reject/", service_orders.ServiceOrderRejectView.as_view(), name="service-order-reject"),
    path("service-orders/<uuid:uuid>/contacted/", service_orders.ServiceOrderContactedView.as_view(), name="service-order-contacted"),
    path("service-orders/<uuid:uuid>/schedule/", service_orders.ServiceOrderScheduleView.as_view(), name="service-order-schedule"),
    path("public-media/", public_media.PublicMediaListView.as_view(), name="public-media"),
    path("public-media/group/", public_media.GroupMediaView.as_view(), name="public-media-group"),
    path("public-media/group/<str:kind>/", public_media.GroupMediaKindView.as_view(), name="public-media-group-kind"),
    path("public-media/branches/<uuid:uuid>/", public_media.BranchMediaView.as_view(), name="public-media-branch"),
    path("public-media/branches/<uuid:uuid>/review/", public_media.BranchMediaReviewView.as_view(), name="public-media-review"),
    path("public-media/branches/<uuid:uuid>/<str:kind>/", public_media.BranchMediaKindView.as_view(), name="public-media-branch-kind"),
    # The patient portal: its own authentication, never a staff session.
    path("portal/<slug:slug>/", include("portal.urls")),
    # The owner portal. Gated by is_platform_staff; see api/platform.py.
    path("platform/plans/", platform.PlanListView.as_view(), name="platform-plans"),
    path("platform/overview/", platform.OverviewView.as_view(), name="platform-overview"),
    path("platform/online/", platform.OnlineView.as_view(), name="platform-online"),
    path("platform/analytics/", platform.AnalyticsView.as_view(), name="platform-analytics"),
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
    # Developer portal, phase 4: full control (api/platform_control.py).
    path("platform/tenants/<uuid:uuid>/edit/", platform_control.TenantEditView.as_view(), name="platform-tenant-edit"),
    path("platform/tenants/<uuid:uuid>/owners/", platform_control.TenantOwnerView.as_view(), name="platform-tenant-owners"),
    path("platform/tenants/<uuid:uuid>/branches/<int:pk>/active/", platform_control.TenantBranchActiveView.as_view(), name="platform-tenant-branch-active"),
    path("platform/tenants/<uuid:uuid>/entitlements/", platform_control.EntitlementsView.as_view(), name="platform-tenant-entitlements"),
    path("platform/tenants/<uuid:uuid>/support/", platform_control.SupportStartView.as_view(), name="platform-tenant-support"),
    path("platform/accounts/<uuid:uuid>/<str:action>/", platform_control.AccountActionView.as_view(), name="platform-account-action"),
    # Developer portal, phase 6: backups and exports (api/platform_backups.py).
    path("platform/backups/", platform_backups.BackupListView.as_view(), name="platform-backups"),
    path("platform/backups/policy/", platform_backups.BackupPolicyView.as_view(), name="platform-backup-policy"),
    path("platform/backups/cpanel/", platform_backups.CpanelBackupView.as_view(), name="platform-backup-cpanel"),
    path("platform/backups/<int:pk>/download/", platform_backups.BackupDownloadView.as_view(), name="platform-backup-download"),
    path("platform/imports/", platform_backups.GroupImportView.as_view(), name="platform-import"),
    path("platform/tenants/<uuid:uuid>/export/", platform_backups.TenantExportView.as_view(), name="platform-tenant-export"),
    path("platform/signups/", signup.SignupQueueView.as_view(), name="platform-signups"),
    path("platform/signups/<int:pk>/approve/", signup.SignupApproveView.as_view(), name="platform-signup-approve"),
    path("platform/signups/<int:pk>/reject/", signup.SignupRejectView.as_view(), name="platform-signup-reject"),
    path("platform/plans/manage/", platform_business.PlanManageView.as_view(), name="platform-plans-manage"),
    path("platform/plans/<int:pk>/", platform_business.PlanDetailView.as_view(), name="platform-plan"),
    path("", include(router.urls)),
]
