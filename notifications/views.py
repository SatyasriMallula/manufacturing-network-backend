import uuid

from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.responses import success_response
from core.pagination import StandardPagination
from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def _unread_count(self, user):
        return Notification.objects.filter(recipient=user, is_read=False).count()

    def get(self, request):
        notifications = Notification.objects.filter(recipient=request.user)
        if request.query_params.get("unread") == "true":
            notifications = notifications.filter(is_read=False)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(notifications, request)
        return success_response(
            message="Notifications fetched",
            data=NotificationSerializer(page, many=True).data,
            unread_count=self._unread_count(request.user),
            **paginator.get_pagination_meta(),
        )

    def patch(self, request):
        """Body: {"action": "mark_read", "ids": [...]}  or  {"action": "mark_all_read"}"""
        action = request.data.get("action")
        unread = Notification.objects.filter(recipient=request.user, is_read=False)

        if action == "mark_read":
            ids = request.data.get("ids")
            if not isinstance(ids, list) or not ids:
                return success_response(message="ids must be a non-empty list", data=None, status_code=400)
            try:
                ids = [uuid.UUID(str(i)) for i in ids]
            except ValueError:
                return success_response(message="Invalid id in list", data=None, status_code=400)
            unread = unread.filter(id__in=ids)
        elif action != "mark_all_read":
            return success_response(message="Invalid action. Use 'mark_read' or 'mark_all_read'.", data=None, status_code=400)

        updated = unread.update(is_read=True, read_at=timezone.now())
        return success_response(
            message="Notifications updated",
            data={"updated": updated, "unread_count": self._unread_count(request.user)},
        )