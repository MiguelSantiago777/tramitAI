from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    verbose_name = "Contas"

    def ready(self) -> None:
        from . import schema  # noqa: F401  (registra a extensão OpenAPI da autenticação)
