from typing import Any

from django import forms
from django.contrib import admin
from django.contrib.auth.password_validation import validate_password
from django.http import HttpRequest

from apps.accounts.models import User

from .models import Tenant
from .services import create_tenant


class TenantCreationForm(forms.ModelForm):
    """Novo escritório pelo admin: cria tudo (titular, configurações, termo de IA)."""

    owner_email = forms.EmailField(label="E-mail do titular")
    owner_name = forms.CharField(label="Nome do titular", max_length=150, required=False)
    owner_password = forms.CharField(
        label="Senha do titular",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Obrigatória se o e-mail ainda não tem conta no TramitAI. "
        "Se já tem, deixe em branco: a pessoa ganha acesso a mais este escritório.",
    )

    class Meta:
        model = Tenant
        fields = ["name", "slug"]
        help_texts = {"slug": "Identificador curto, sem espaços. Vazio = gerado pelo nome."}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        email = data.get("owner_email")
        password = data.get("owner_password")
        if email and not User.objects.filter(email__iexact=email).exists():
            if not password:
                self.add_error("owner_password", "Defina a senha do titular (conta nova).")
            else:
                try:
                    validate_password(password)
                except forms.ValidationError as exc:
                    self.add_error("owner_password", exc)
        return data


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "status", "created_at"]
    search_fields = ["name", "slug"]
    list_filter = ["status"]

    def get_form(
        self, request: HttpRequest, obj: Any = None, change: bool = False, **kwargs: Any
    ) -> Any:
        if obj is None:
            kwargs["form"] = TenantCreationForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request: HttpRequest, obj: Any = None) -> Any:
        if obj is None:
            return ["name", "slug", "owner_email", "owner_name", "owner_password"]
        return super().get_fields(request, obj)

    def save_model(self, request: HttpRequest, obj: Tenant, form: Any, change: bool) -> None:
        if change:
            super().save_model(request, obj, form, change)
            return
        created = create_tenant(
            name=form.cleaned_data["name"],
            slug=form.cleaned_data.get("slug") or None,
            owner_email=form.cleaned_data["owner_email"],
            owner_full_name=form.cleaned_data.get("owner_name") or "",
            owner_password=form.cleaned_data.get("owner_password") or None,
        )
        # O admin segue usando `obj` (mensagem, log e redirecionamento).
        obj.pk = created.tenant.pk
        obj.slug = created.tenant.slug
        obj._state.adding = False
