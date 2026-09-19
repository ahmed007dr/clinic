"""How a one-time code reaches a person — one channel today, room for more.

The verification logic (`PortalVerification`: hashed code, ten minutes, five
guesses, once) never knows *how* a code was delivered. A channel only delivers.
E-mail is the default and the only one registered now; SMS is added by
registering a second channel when a provider is enabled (docs/15, D5) — nothing
in the signup or profile flows changes.

A channel that cannot deliver returns False, and the caller's answer to the
person never depends on it (no oracle: a code request looks the same whether or
not anything was sent).
"""

from . import mail

PURPOSES = ("signup", "email_change")


class OtpChannel:
    name = ""

    def available(self, tenant):
        """Whether this channel is switched on for the group."""
        raise NotImplementedError

    def send(self, *, tenant, branch, destination, code, purpose):
        """Deliver `code` to `destination`. True if it was handed to the provider."""
        raise NotImplementedError


class EmailChannel(OtpChannel):
    name = "email"

    def available(self, tenant):
        # Whether a mail server exists is decided when sending (sender_for);
        # the channel itself is always offered.
        return True

    def send(self, *, tenant, branch, destination, code, purpose):
        return mail.send_verification_code(
            tenant, branch, destination, code, purpose
        )


_REGISTRY = {EmailChannel.name: EmailChannel()}
DEFAULT = EmailChannel.name


def register(channel):
    """Add a channel (e.g. SMS) once its provider is enabled."""
    _REGISTRY[channel.name] = channel


def channel_for(tenant, name=None):
    """The channel to use: the one asked for if it is registered and on for
    this group, else the default (e-mail)."""
    channel = _REGISTRY.get(name or DEFAULT)
    if channel is None or not channel.available(tenant):
        channel = _REGISTRY[DEFAULT]
    return channel
