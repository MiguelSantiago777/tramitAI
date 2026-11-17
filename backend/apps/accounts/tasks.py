import logging

from celery import shared_task
from django.core.mail import send_mail

from .models import User
from .services import password_reset_link

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, acks_late=True)
def send_password_reset_email(self, user_id: str) -> None:  # type: ignore[no-untyped-def]
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return
    link = password_reset_link(user)
    try:
        send_mail(
            subject="Redefinir sua senha no TramitAI",
            message=(
                f"Olá{', ' + user.full_name.split(' ')[0] if user.full_name else ''}!\n\n"
                "Recebemos um pedido para redefinir a senha da sua conta no TramitAI.\n"
                f"Para criar uma senha nova, abra o link abaixo (vale por 3 dias):\n\n{link}\n\n"
                "Se não foi você, ignore este e-mail: sua senha continua a mesma.\n"
            ),
            from_email=None,
            recipient_list=[user.email],
        )
    except Exception as exc:
        # Só o tipo: a mensagem de erro do SMTP pode trazer o endereço.
        logger.warning("password reset: falha no envio (%s) user %s", type(exc).__name__, user_id)
        raise self.retry(exc=exc, countdown=60 * 2**self.request.retries) from exc


@shared_task(bind=True, max_retries=3, acks_late=True)
def send_invite_email(self, membership_id: str, invited_by_name: str) -> None:  # type: ignore[no-untyped-def]
    from .models import Membership
    from .team import invite_link

    membership = (
        Membership.objects.select_related("user", "tenant")
        .filter(pk=membership_id, is_active=True)
        .first()
    )
    if membership is None or membership.user.has_usable_password():
        return
    user = membership.user
    try:
        send_mail(
            subject=f"Convite para a equipe do {membership.tenant.name} no TramitAI",
            message=(
                f"Olá{', ' + user.full_name.split(' ')[0] if user.full_name else ''}!\n\n"
                f"{invited_by_name} convidou você para a equipe do {membership.tenant.name} "
                "no TramitAI.\n\n"
                "Para entrar, crie sua senha neste link (vale por 3 dias):\n\n"
                f"{invite_link(user)}\n\n"
                f"Depois é só entrar com o e-mail {user.email}.\n"
            ),
            from_email=None,
            recipient_list=[user.email],
        )
    except Exception as exc:
        logger.warning(
            "convite: falha no envio (%s) membership %s", type(exc).__name__, membership_id
        )
        raise self.retry(exc=exc, countdown=60 * 2**self.request.retries) from exc
