"""Notifications — per user, not per clinic."""

from rest_framework import serializers

from notifications.models import Notification

from .common import ClinicSerializer


class NotificationSerializer(ClinicSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "uuid", "serial_number", "type", "type_label",
            "title", "message", "is_read", "created_at",
        ]
        # Everything is server-generated; the only thing a client changes is
        # whether it has been read, and that has its own endpoint so it cannot
        # be bundled with an edit of the message text.
        read_only_fields = fields
