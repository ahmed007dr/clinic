"""Time-based one-time codes (RFC 6238) — the second step of a platform sign-in.

The standard algorithm, from the standard library: any authenticator app
(Google Authenticator, Microsoft Authenticator, Authy…) shows the same six
digits every 30 seconds from the shared secret. No third-party package on the
server for the one thing that guards every clinic at once.

Recovery codes are for the lost phone: eight one-time codes shown once at
enrolment and kept only as hashes, like passwords.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from django.contrib.auth.hashers import check_password, make_password

DIGITS = 6
STEP = 30
#: Codes one step either side are accepted, for a phone clock a little off.
WINDOW = 1
ISSUER = "Clinic Platform"
RECOVERY_CODES = 8


def new_secret():
    """160 random bits, base32 — what authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _code(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10 ** DIGITS).zfill(DIGITS)


def code_at(secret, moment=None):
    return _code(secret, int((moment if moment is not None else time.time()) // STEP))


def verify(secret, code, moment=None):
    """True for the current code, or one step either side."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if not secret or len(code) != DIGITS:
        return False
    counter = int((moment if moment is not None else time.time()) // STEP)
    return any(
        hmac.compare_digest(_code(secret, counter + drift), code)
        for drift in range(-WINDOW, WINDOW + 1)
    )


def provisioning_uri(secret, account):
    label = quote(f"{ISSUER}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&digits={DIGITS}&period={STEP}"


def qr_svg(uri):
    """The enrolment QR code as inline SVG text (the `qrcode` package, pure
    Python). None if the package is missing — the page then shows the secret
    to type in by hand, which every authenticator app also accepts."""
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return None
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return image.to_string(encoding="unicode")


def new_recovery_codes():
    """(codes to show once, hashes to store)."""
    codes = [f"{secrets.randbelow(10 ** 5):05d}-{secrets.randbelow(10 ** 5):05d}" for _ in range(RECOVERY_CODES)]
    return codes, [make_password(code) for code in codes]


def use_recovery_code(user, code):
    """Consume one recovery code if it matches. Returns True when used."""
    code = str(code or "").strip()
    for stored in list(user.totp_recovery_codes or []):
        if check_password(code, stored):
            user.totp_recovery_codes = [c for c in user.totp_recovery_codes if c != stored]
            user.save(update_fields=["totp_recovery_codes"])
            return True
    return False
