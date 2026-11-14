import logging

from django.conf import settings
from django.core.mail import send_mass_mail
from django.db import transaction

from users.models import User
from .models import Notification

logger = logging.getLogger(__name__)


def users_in_org(org_id, roles):
    return User.objects.filter(
        organization_id=org_id, is_active=True, groups__name__in=roles
    ).distinct()


def notify(users, notification_type, title, message, target_type, target_id, actor=None):
    recipients = [u for u in users if not (actor and u.pk == actor.pk)]  # never notify the actor
    if not recipients:
        return

    Notification.objects.bulk_create([
        Notification(
            recipient=u, notification_type=notification_type, title=title,
            message=message, target_type=target_type, target_id=target_id,
        )
        for u in recipients
    ])

    if settings.NOTIFICATION_EMAILS_ENABLED:
        emails = [u.email for u in recipients]
        # Runs only after the surrounding transaction commits.
        # To move to Celery later, change this one line to: send_emails.delay(emails, title, message)
        transaction.on_commit(lambda: _send_emails(emails, title, message))


def _send_emails(emails, title, message):
    try:
        # One email per person, so recipients never see each other's addresses
        send_mass_mail(
            [(title, message, settings.DEFAULT_FROM_EMAIL, [e]) for e in emails],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send notification emails")