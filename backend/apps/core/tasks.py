from celery import shared_task

from . import trash


@shared_task
def purge_trash() -> int:
    """Apaga de vez o que está na lixeira há mais de 30 dias."""
    return trash.purge_expired()
