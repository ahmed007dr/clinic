"""Mounted by api/urls.py at `/api/portal/<slug>/`."""

from django.urls import path

from . import account, catalog, my_bookings, orders, registration, views

app_name = "portal"

urlpatterns = [
    path("auth/accept-invite/", views.AcceptInviteView.as_view(), name="accept-invite"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/otp/request/", views.OtpRequestView.as_view(), name="otp-request"),
    path("auth/otp/verify/", views.OtpVerifyView.as_view(), name="otp-verify"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    # Creating an account, proved by a code (docs/15, Phase 2) — and the profile.
    path("account/start/", account.SignupStartView.as_view(), name="account-start"),
    path("account/verify/", account.SignupVerifyView.as_view(), name="account-verify"),
    path("me/profile/", account.ProfileView.as_view(), name="profile"),
    path("me/email/", account.EmailChangeStartView.as_view(), name="email-change"),
    path("me/email/verify/", account.EmailChangeVerifyView.as_view(), name="email-change-verify"),
    path("register/options/", registration.RegisterOptionsView.as_view(), name="register-options"),
    path("register/", registration.RegisterView.as_view(), name="register"),
    path("links/", registration.PublicLinksView.as_view(), name="links"),
    path("about/", registration.PublicAboutView.as_view(), name="about"),
    # The public catalogue: service → the clinics that offer it → its doctors (docs/15, Phase 3).
    path("catalog/services/", catalog.CatalogServicesView.as_view(), name="catalog-services"),
    path("catalog/regions/", catalog.CatalogRegionsView.as_view(), name="catalog-regions"),
    path("catalog/services/<uuid:service>/branches/", catalog.CatalogBranchesView.as_view(), name="catalog-branches"),
    path(
        "catalog/services/<uuid:service>/branches/<uuid:branch>/doctors/",
        catalog.CatalogDoctorsView.as_view(), name="catalog-doctors",
    ),
    path("catalog/availability/", catalog.CatalogAvailabilityView.as_view(), name="catalog-availability"),
    path("catalog/availability/days/", catalog.CatalogAvailableDaysView.as_view(), name="catalog-availability-days"),
    # A clinic's times for a service across its doctors — what «طلباتي» offers (docs/16).
    path("catalog/availability/branch-days/", catalog.CatalogBranchDaysView.as_view(), name="catalog-branch-days"),
    path("catalog/availability/branch-times/", catalog.CatalogBranchTimesView.as_view(), name="catalog-branch-times"),
    path("booking/options/", views.BookingOptionsView.as_view(), name="booking-options"),
    # «طلباتي» — the customer's service orders (docs/16).
    path("orders/", orders.OrdersView.as_view(), name="orders"),
    path("orders/<uuid:uuid>/", orders.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<uuid:uuid>/cancel/", orders.OrderCancelView.as_view(), name="order-cancel"),
    path("appointments/", views.AppointmentsView.as_view(), name="appointments"),
    path("appointments/<uuid:uuid>/", my_bookings.AppointmentDetailView.as_view(), name="appointment-detail"),
    path("appointments/<uuid:uuid>/cancel/", my_bookings.AppointmentCancelView.as_view(), name="appointment-cancel"),
    path("appointments/<uuid:uuid>/reschedule/", my_bookings.AppointmentRescheduleView.as_view(), name="appointment-reschedule"),
    path("appointments/<uuid:uuid>/pay/", views.AppointmentPayView.as_view(), name="appointment-pay"),
    path("pay/options/", views.PayOptionsView.as_view(), name="pay-options"),
    path("visits/", views.VisitsView.as_view(), name="visits"),
    path("prescriptions/", views.PrescriptionsView.as_view(), name="prescriptions"),
    path("prescriptions/<uuid:uuid>/", views.PrescriptionDetailView.as_view(), name="prescription"),
    path("lab-results/", views.LabResultsView.as_view(), name="lab-results"),
    path("attachments/", views.AttachmentsView.as_view(), name="attachments"),
    path(
        "attachments/<uuid:uuid>/download/",
        views.AttachmentDownloadView.as_view(),
        name="attachment-download",
    ),
    path("payments/", views.PaymentsView.as_view(), name="payments"),
    path("treatment-plans/", views.TreatmentPlansView.as_view(), name="treatment-plans"),
    path("allergies/", views.AllergiesView.as_view(), name="allergies"),
]
