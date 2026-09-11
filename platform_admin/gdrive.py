"""Google Drive for the platform's backups, through a service account.

The service account's JSON key and the folder id are entered in the developer
portal (vault kind `google_drive`). The folder must be in a **Shared Drive**
the service account is a member of: since 2024 Google gives service accounts
no storage of their own, so uploading into a folder in someone's personal
"My Drive" fails with a quota error even when it is shared with them.

Standard library and `cryptography` only: a JWT signed with the key (RS256)
is exchanged for an access token (OAuth 2.0 JWT bearer grant), then Drive v3.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 60
SCOPE = "https://www.googleapis.com/auth/drive"
TOKEN_URI = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"


class DriveError(RuntimeError):
    """The message is for the operator."""


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _assertion(account):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64(json.dumps({
        "iss": account["client_email"], "scope": SCOPE, "aud": account.get("token_uri") or TOKEN_URI,
        "iat": now, "exp": now + 3600,
    }).encode())
    try:
        key = serialization.load_pem_private_key(account["private_key"].encode(), password=None)
    except (ValueError, TypeError):
        raise DriveError("المفتاح الخاص في ملف Service Account غير صالح.")
    signature = key.sign(f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{claims}.{_b64(signature)}"


def _open(request):
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = json.loads(error.read().decode()).get("error", {})
            detail = detail.get("message", "") if isinstance(detail, dict) else str(detail)
        except Exception:  # noqa: BLE001
            pass
        raise DriveError(f"رفض Google الطلب ({error.code}) {detail}".strip())
    except (urllib.error.URLError, TimeoutError):
        raise DriveError("تعذّر الاتصال بـ Google.")


def access_token(config):
    try:
        account = json.loads(config["service_account_json"])
    except (KeyError, ValueError):
        raise DriveError("ملف Service Account غير صالح.")
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": _assertion(account),
    }).encode()
    request = urllib.request.Request(account.get("token_uri") or TOKEN_URI, data=body, method="POST")
    _, _, raw = _open(request)
    token = json.loads(raw.decode()).get("access_token")
    if not token:
        raise DriveError("لم يُصدر Google رمز دخول.")
    return token


def _authorized(url, token, **kwargs):
    headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
    return urllib.request.Request(url, headers=headers, **kwargs)


def check(config):
    """The folder's name, proving the key works and the folder is reachable."""
    token = access_token(config)
    query = urllib.parse.urlencode({"fields": "id,name", "supportsAllDrives": "true"})
    _, _, raw = _open(_authorized(f"{API}/files/{config['folder_id']}?{query}", token))
    return json.loads(raw.decode()).get("name", config["folder_id"])


def upload(config, path, name=None, mime="application/octet-stream"):
    """Upload one file into the folder (resumable upload); returns its id."""
    token = access_token(config)
    metadata = json.dumps({"name": name or os.path.basename(path), "parents": [config["folder_id"]]}).encode()
    size = os.path.getsize(path)
    start = _authorized(
        f"{UPLOAD}/files?uploadType=resumable&supportsAllDrives=true", token, data=metadata, method="POST",
        headers={"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": mime,
                 "X-Upload-Content-Length": str(size)},
    )
    _, headers, _ = _open(start)
    location = headers.get("Location") or headers.get("location")
    if not location:
        raise DriveError("لم يبدأ Google عملية الرفع.")
    with open(path, "rb") as handle:
        put = urllib.request.Request(
            location, data=handle, method="PUT", headers={"Content-Type": mime, "Content-Length": str(size)},
        )
        _, _, raw = _open(put)
    return json.loads(raw.decode()).get("id", "")


def delete(config, file_id):
    token = access_token(config)
    _open(_authorized(f"{API}/files/{file_id}?supportsAllDrives=true", token, method="DELETE"))
