import uuid
from typing import Any, ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


def normalize_email_address(email: str) -> str:
    return email.strip().lower()


class UserManager(BaseUserManager["User"]):
    def create_user(self, email: str, password: str | None = None, **extra: Any) -> User:
        if not email:
            raise ValueError("E-mail é obrigatório.")
        user = self.model(email=normalize_email_address(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Usuário global (control plane). O vínculo com escritórios fica em Membership.

    `is_superuser` aqui é só do Django admin; não tem relação com o role do Postgres.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("e-mail", unique=True)
    full_name = models.CharField("nome completo", max_length=200, blank=True, default="")
    oab_number = models.CharField("número OAB", max_length=20, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.email


class Membership(models.Model):
    """Vínculo usuário ↔ escritório (control plane: a autenticação lê antes do tenant ativo)."""

    class Role(models.TextChoices):
        OWNER = "OWNER", "Titular"
        LAWYER = "LAWYER", "Advogado(a)"
        STAFF = "STAFF", "Equipe"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.PROTECT, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "vínculo"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tenant"], name="membership_user_tenant_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.tenant_id} ({self.role})"
