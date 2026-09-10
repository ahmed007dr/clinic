"""Notifications — scoped to the signed-in user, not the clinic."""

from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response

from api.permissions import IsClinicMember
from api.serializers.notifications import NotificationSerializer
from api.viewsets import ReadOnlyClinicViewSet
from notifications.models import Notification


class NotificationViewSet(ReadOnlyClinicViewSet):
    """One user's notifications.

    `branch_field = None` because these are addressed to a person, not a place:
    a doctor who covers another branch for a day must still see their own
    alerts. The narrowing is by user instead, and it is applied to the queryset
    rather than checked per object — so a UUID belonging to a colleague is an
    ordinary 404, never a leak.
    """

    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsClinicMember]
    branch_field = None
    ordering = ["-created_at"]

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.filter(user=self.request.user)
        if self.request.query_params.get("unread") == "1":
            queryset = queryset.filter(is_read=False)
        return queryset

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        """Drives the badge in the header, so it is deliberately cheap."""
        return Response(
            {"count": self.get_queryset().filter(is_read=False).count()}
        )

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, uuid=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"updated": updated, "at": timezone.now()})
