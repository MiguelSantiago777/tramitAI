from typing import Any

from rest_framework import serializers

from apps.clientes.models import Client, ClientTermAcceptance
from apps.clientes.selectors import document_in_use
from apps.core.br import is_valid_cnpj, is_valid_cpf, normalize_br_phone, normalize_document


class ClientSerializer(serializers.ModelSerializer):
    # Aceita com pontuação (até 18 caracteres); grava normalizado (máx. 14).
    cpf_cnpj = serializers.CharField(
        required=False, allow_blank=True, max_length=20, label="CPF/CNPJ"
    )
    phone = serializers.CharField(
        source="phone_e164", required=False, allow_blank=True, max_length=30
    )

    class Meta:
        model = Client
        fields = [
            "id",
            "kind",
            "name",
            "cpf_cnpj",
            "phone",
            "email",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Informe o nome.")
        return value

    def validate_cpf_cnpj(self, value: str) -> str:
        return normalize_document(value)

    def validate_phone(self, value: str) -> str:
        if not value.strip():
            return ""
        phone = normalize_br_phone(value)
        if phone is None:
            raise serializers.ValidationError("Telefone inválido. Use DDD + número.")
        return phone

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance: Client | None = self.instance
        kind = attrs.get("kind", instance.kind if instance else Client.Kind.PERSON)
        document = attrs.get("cpf_cnpj", instance.cpf_cnpj if instance else "")
        if document:
            if kind == Client.Kind.PERSON and not is_valid_cpf(document):
                raise serializers.ValidationError({"cpf_cnpj": "CPF inválido."})
            if kind == Client.Kind.COMPANY and not is_valid_cnpj(document):
                raise serializers.ValidationError({"cpf_cnpj": "CNPJ inválido."})
            if document_in_use(document, exclude_id=instance.pk if instance else None):
                raise serializers.ValidationError(
                    {"cpf_cnpj": "Já existe um cliente com este CPF/CNPJ."}
                )
        return attrs


class ClientFilterSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=Client.Status.choices, required=False, allow_blank=True, default=""
    )


class TermAcceptanceSerializer(serializers.ModelSerializer):
    term_version = serializers.IntegerField(source="term_version.version", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()
    accepted_at = serializers.DateTimeField(required=False)

    class Meta:
        model = ClientTermAcceptance
        fields = [
            "id",
            "term_version",
            "accepted_at",
            "channel",
            "evidence",
            "recorded_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "term_version", "recorded_by_name", "created_at"]

    def get_recorded_by_name(self, obj: ClientTermAcceptance) -> str:
        user = obj.recorded_by
        return (user.full_name or user.email) if user else ""
