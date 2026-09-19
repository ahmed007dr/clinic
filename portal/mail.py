"""Emails the portal sends to a patient, through the clinic's own mail server.

Same rule as `billing.notify`: a failure to send is logged, never raised — and
with no mail server set up anywhere nothing is sent. The portal's answer to a
code request never depends on whether a message actually left (no oracle).
"""

import logging

from notifications.maillog import MASK, deliver, mask_links

from .models import CODE_TTL

logger = logging.getLogger(__name__)


def send_login_codes(tenant, email, entries):
    """`entries` is [(patient, code)] — every account behind one address, since
    a household often shares an email. One message carries them all."""
    from platform_admin.mailer import sender_for

    minutes = int(CODE_TTL.total_seconds() // 60)
    lines = [f"رمز الدخول إلى بوابة {tenant.name}:", ""]
    for patient, code in entries:
        lines.append(f"{patient.name}: {code}" if len(entries) > 1 else code)
    lines += ["", f"الرمز صالح {minutes} دقائق ولمرة واحدة. لا تشاركه مع أحد.",
              "إن لم تطلبه فتجاهل هذه الرسالة."]
    try:
        branch = entries[0][0].branch
        connection, sender = sender_for(branch=branch, customer=tenant)
        # The log keeps who was sent a code and when — never the code, which
        # would let anyone who reads the log sign in as that patient.
        logged = [f"رمز الدخول إلى بوابة {tenant.name}:", ""]
        for patient, _code in entries:
            logged.append(f"{patient.name}: {MASK}" if len(entries) > 1 else MASK)
        logged += lines[len(entries) + 2:]
        return deliver(
            kind="portal_login_code", tenant=tenant, branch=branch, to=email,
            subject=f"رمز الدخول إلى بوابة {tenant.name}", body="\n".join(lines),
            log_body="\n".join(logged), connection=connection, sender=sender,
        )
    except Exception:  # noqa: BLE001 — see the module docstring
        logger.exception("Could not email a portal login code")
        return False


def send_invitation(tenant, patient, url, hours):
    """The single-use link that lets a patient set their portal password."""
    from platform_admin.mailer import sender_for

    to = (patient.email or "").strip()
    if not to:
        return False
    lines = [
        f"مرحباً {patient.name}،", "",
        f"دعتك {tenant.name} إلى بوابة المرضى لمتابعة مواعيدك وروشتاتك ونتائجك.",
        "افتح الرابط التالي لتعيين كلمة المرور:", url, "",
        f"الرابط صالح {hours} ساعة ولمرة واحدة.",
    ]
    try:
        connection, sender = sender_for(branch=patient.branch, customer=tenant)
        body = "\n".join(lines)
        return deliver(
            kind="portal_invitation", tenant=tenant, branch=patient.branch, to=to,
            subject=f"دعوة إلى بوابة {tenant.name}", body=body,
            # The link is a single-use credential: not kept.
            log_body=mask_links(body), connection=connection, sender=sender,
        )
    except Exception:  # noqa: BLE001 — see the module docstring
        logger.exception("Could not email a portal invitation")
        return False
