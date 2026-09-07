from django.conf import settings


def clinic_branding(request):
    """Shared clinic_name/clinic_logo/footer_text, previously duplicated in
    nearly every view's context dict. Prefers the logged-in user's branch
    (falls back to the CLINIC_NAME/CLINIC_LOGO/FOOTER_TEXT settings for
    anonymous users, users without a branch, or branches missing a value)."""
    branch = None
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        branch = getattr(user, 'branch', None)

    return {
        'clinic_name': branch.name if branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': branch.logo.url if branch and branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': branch.footer_text if branch and branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.'),
    }
