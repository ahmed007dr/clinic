"""Mounted by api/urls.py at `/api/portal/<slug>/`."""

from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("auth/accept-invite/", views.AcceptInviteView.as_view(), name="accept-invite"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("appointments/", views.AppointmentsView.as_view(), name="appointments"),
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
