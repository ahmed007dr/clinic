
from pathlib import Path
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool('DJANGO_DEBUG', default=False)

ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=[])

CSRF_TRUSTED_ORIGINS = env.list('DJANGO_CSRF_TRUSTED_ORIGINS', default=[])


# --- Transport security -------------------------------------------------------
# Secure by default and relaxed only when DEBUG is on, so a local HTTP session
# still works while a deployment gets the hardened values without anyone
# remembering to set them. Each stays overridable, because "is this deployment
# behind TLS" is a property of the environment, not of the code.
#
# Django already defaults the rest of the headers sensibly and they are not
# repeated here: SECURE_CONTENT_TYPE_NOSNIFF, X_FRAME_OPTIONS = 'DENY',
# SECURE_REFERRER_POLICY, SECURE_CROSS_ORIGIN_OPENER_POLICY and
# SESSION_COOKIE_HTTPONLY are all already on.
SESSION_COOKIE_SECURE = env.bool('DJANGO_SESSION_COOKIE_SECURE', default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool('DJANGO_CSRF_COOKIE_SECURE', default=not DEBUG)

# Redirects http:// to https://. Read the proxy note below before deploying:
# behind a load balancer that terminates TLS, Django cannot tell the original
# request was secure, so this redirects forever unless the proxy's header is
# trusted. That is why the header is a separate, explicit opt-in — trusting a
# forwarded header blindly lets a client claim its own connection was secure.
SECURE_SSL_REDIRECT = env.bool('DJANGO_SECURE_SSL_REDIRECT', default=not DEBUG)
if env.bool('DJANGO_TRUST_PROXY_SSL_HEADER', default=False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS is opt-in and off by default, unlike the three settings above, because it
# is the one that cannot be quickly undone: browsers cache it for max-age and
# will refuse plain HTTP to this domain — and with subdomains, everything under
# it — for that whole period, ignoring any later change. Enable it per
# deployment once HTTPS is confirmed everywhere, starting with a small max-age
# (e.g. 3600) and raising it. Until then `manage.py check --deploy` reports
# W004, which is an accurate description of the deployment, not a defect here.
SECURE_HSTS_SECONDS = env.int('DJANGO_SECURE_HSTS_SECONDS', default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', default=bool(SECURE_HSTS_SECONDS)
)
SECURE_HSTS_PRELOAD = env.bool('DJANGO_SECURE_HSTS_PRELOAD', default=False)




# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    "tenants",
    "subscriptions",
    "platform_admin",
    "accounts",
    "employees",
    "patients",
    "services",
    "appointments",
    "medical",
    "billing",
    "reports",
    "branches",
    "audit",
    "notifications",
    'dashboard',

    # REST API consumed by the React front end in frontend/. Mounted under
    # /api/; the server-rendered screens keep their own URLs and keep working.
    "rest_framework",
    "api",
    # Patient portal — its own accounts and sessions; see docs/12.
    "portal",

]

REST_FRAMEWORK = {
    # Session authentication, deliberately, and not tokens. TenantMiddleware
    # binds the tenant — and with it the PostgreSQL row-level security
    # context — from request.user, and middleware runs before the view. DRF
    # token authentication runs *inside* the view, so the tenant would be
    # bound while the user was still anonymous and every query in the request
    # would return nothing. See api/views/auth.py.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Fails closed: a view that forgets to declare permissions is closed, not
    # open. Every clinic viewset narrows this further.
    "DEFAULT_PERMISSION_CLASSES": [
        "api.permissions.IsClinicMember",
    ],
    "DEFAULT_PAGINATION_CLASS": "api.pagination.ClinicPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Password guessing is the only unauthenticated write in the API.
        "login": "10/min",
        "portal_login": "10/min",
        # Public self-registration: generous for a family, useless for a bot.
        "portal_register": "10/hour",
        # Asking to open a clinic group (api/signup.py).
        "signup": "5/hour",
    },
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # A multi-clinic doctor's chosen clinic, from the session (accounts.roles).
    'accounts.middleware.ActiveBranchMiddleware',
    # A platform session is only ever one completed with a one-time code.
    'accounts.middleware.PlatformTwoFactorMiddleware',
    # A developer's time-limited "login as" support session.
    'accounts.middleware.SupportSessionMiddleware',
    # "Online now" / "last seen" for the platform portal.
    'accounts.middleware.LastSeenMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # Must follow AuthenticationMiddleware — the tenant comes from request.user.
    "tenants.middleware.TenantMiddleware",

    "audit.middleware.ThreadLocalMiddleware",
    "audit.middleware.AuditMiddleware",

]

ROOT_URLCONF = 'project.urls'
AUTH_USER_MODEL = "accounts.User"

CLINIC_NAME = "Dr-ahmed"
CLINIC_LOGO = "images/logo.svg"
FOOTER_TEXT = "Copyright &copy; 2025 All rights reserved."

LOGIN_URL = '/accounts/login/' 
LOGIN_REDIRECT_URL = '/appointments/'
LOGOUT_REDIRECT_URL = '/accounts/login/' 


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'utils.context_processors.clinic_branding',
                'accounts.context_processors.roles',
            ],
        },
    },
]

WSGI_APPLICATION = 'project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

# DATABASE_URL drives this. PostgreSQL in every real environment; the SQLite
# default only exists so a fresh checkout runs without configuration.
# DigitalOcean Managed PostgreSQL requires SSL, so its URL ends in ?sslmode=require
DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Cairo"
USE_I18N = True
USE_TZ = False


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / "static",
    # The React build (frontend/dist/spa/*), served from /static/spa/. Source
    # stays in frontend/; only the compiled output is collected, so deploying
    # the new front end is the same collectstatic step as before.
    BASE_DIR / "frontend" / "dist",
]
# collectstatic target for deployment. Generated output — gitignored.
# Env-configurable because shared hosting decides where these live. On cPanel
# the web server only serves what is under ~/public_html, so collectstatic has
# to write there — e.g. DJANGO_STATIC_ROOT=/home/<account>/public_html/static.
STATIC_ROOT = Path(env.str('DJANGO_STATIC_ROOT', default=str(BASE_DIR / "staticfiles")))

MEDIA_URL = env.str('DJANGO_MEDIA_URL', default='/media/')
MEDIA_ROOT = Path(env.str('DJANGO_MEDIA_ROOT', default=str(BASE_DIR / "media")))

# --- Medical attachments (doc §61) -------------------------------------------
# Deliberately NOT under MEDIA_ROOT. Anything in MEDIA_ROOT is a candidate for
# the web server to serve directly, and a file served that way has bypassed
# every permission check the application makes. With DEBUG = True Django serves
# MEDIA_ROOT itself with no authentication, so a patient's scan would be
# readable by anyone who guessed the URL. These live somewhere no server is
# configured to reach, and are streamed only by an authenticated view.
MEDICAL_ATTACHMENTS_ROOT = Path(
    env.str('DJANGO_MEDICAL_ATTACHMENTS_ROOT',
            default=str(BASE_DIR / 'private' / 'attachments'))
)
MEDICAL_ATTACHMENT_MAX_BYTES = env.int(
    'DJANGO_MEDICAL_ATTACHMENT_MAX_BYTES', default=10 * 1024 * 1024
)

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'



EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# No default, matching EMAIL_HOST_USER/PASSWORD below. It used to fall back to
# `mail.2odays.com` — the host SEC-001 rotated away from after its credentials
# leaked, and which no longer resolves. A stale default is worse than a missing
# one here: with the user and password already required, the only thing the
# fallback could do was point correct credentials at the wrong server.
EMAIL_HOST = env('EMAIL_HOST')
EMAIL_PORT = env.int('EMAIL_PORT', default=465)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=False)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)

# Encrypts the developer portal's stored keys (platform_admin/vault.py).
PLATFORM_VAULT_KEY = env('PLATFORM_VAULT_KEY', default='')
