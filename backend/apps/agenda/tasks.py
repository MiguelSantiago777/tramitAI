from celery import shared_task

from . import services


@shared_task
def create_event_reminders() -> int:
    return services.create_event_reminders()
