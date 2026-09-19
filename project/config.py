"""
Environment switch — development or production, from this file only.

Flip IS_PRODUCTION and restart. settings.py reads every value below from here;
secrets (SECRET_KEY, database, SMTP, vault key) stay in .env and never move.

The front end has no switch of its own: `npm run dev` uses
frontend/.env.development and `npm run build` uses frontend/.env.production.
Only the domain is written in both places — keep PRIMARY_DOMAIN here and
VITE_BASE_URL in frontend/.env.production in step.
"""

import os

#IS_PRODUCTION = False  # development
IS_PRODUCTION = True  # production


#USE_POSTGRES = False  # SQLite  (db.sqlite3 next to manage.py)
USE_POSTGRES = True  # PostgreSQL (connection string: POSTGRES_URL in .env)

# Independent of IS_PRODUCTION on purpose: you can run development mode against
# PostgreSQL, or a throwaway production check against SQLite. The PostgreSQL
# password is a secret, so only the switch lives here; the connection string is
#   POSTGRES_URL=postgres://USER:PASSWORD@HOST:PORT/DBNAME
# in .env (append ?sslmode=require for a managed host).

# A real environment variable beats the two switches above, so a test run, a CI
# job or a one-off command can choose without editing — and accidentally
# committing — this file:
#     DJANGO_ENV=development|production      DJANGO_DB=sqlite|postgres
_env = os.environ.get('DJANGO_ENV', '').strip().lower()
if _env in ('development', 'production'):
    IS_PRODUCTION = _env == 'production'
_db = os.environ.get('DJANGO_DB', '').strip().lower()
if _db in ('sqlite', 'postgres'):
    USE_POSTGRES = _db == 'postgres'

if IS_PRODUCTION:
    # ========== PRODUCTION ==========
    DEBUG = False

    PRIMARY_DOMAIN = 'dr-clinic.xpro24.com'

    ALLOWED_HOSTS = [PRIMARY_DOMAIN, f'www.{PRIMARY_DOMAIN}']

    # The API and the React build are served by this same Django, so the
    # browser is always same-origin: no CORS. The session cookie stays
    # host-only on purpose — a `.xpro24.com` domain would share it with every
    # other project on the portfolio's parent domain.
    CSRF_TRUSTED_ORIGINS = [
        f'https://{PRIMARY_DOMAIN}',
        f'https://www.{PRIMARY_DOMAIN}',
    ]

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True

    # Where the browser reaches Django (used in links and emails).
    BASE_URL = f'https://{PRIMARY_DOMAIN}'

else:
    # ========== DEVELOPMENT ==========
    DEBUG = True

    PRIMARY_DOMAIN = 'localhost'

    ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

    # 8000 = Django itself, 5173 = the Vite dev server (proxies to Django but
    # keeps its own Origin header, which CSRF checks).
    CSRF_TRUSTED_ORIGINS = [
        'http://localhost:5173',
        'http://127.0.0.1:5173',
        'http://localhost:8000',
        'http://127.0.0.1:8000',
    ]

    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False

    BASE_URL = 'http://127.0.0.1:8000'
