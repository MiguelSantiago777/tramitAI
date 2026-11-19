from typing import Any

from rest_framework import serializers

from apps.clientes.models import Client, ClientNote, ClientTermAcceptance, Tag
from apps.clientes.selectors import document_owner
from apps.core.br import is_valid_cnpj, is_valid_cpf, normalize_br_phone, normalize_document
from apps.core.serializers import TenantScopedPrimaryKeyRelatedField
from apps.processos.models import LegalCase


class ClientSerializer(serializers.ModelSerializer):
    # Aceita com pontuação (até 18 caracteres); grava normalizado (máx. 14).
    cpf_cnpj = serializers.CharField(
        required=False, allow_blank=True, max_length=20, label="CPF/CNPJ"
    )
    phone = serializers.CharField(
        source="phone_e164", required=False, allow_blank=True, max_length=30
    )
    tags = serializers.SerializerMethodField()
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False, max_length=20
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
            "tags",
            "tag_ids",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_tags(self, obj: Client) -> list[dict[str, str]]:
        return [
            {"id": str(ct.tag.pk), "name": ct.tag.name, "color": ct.tag.color}
            for ct in obj.client_tags.all()
        ]

    def validate_tag_ids(self, value: list[Any]) -> list[Tag]:
        # Só etiquetas do escritório ativo (o FK do banco não respeita RLS).
        tags = list(Tag.objects.filter(pk__in=value))
        if len(tags) != len(set(value)):
            raise serializers.ValidationError("Etiqueta inválida.")
        return tags

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
            owner = document_owner(document, exclude_id=instance.pk if instance else None)
            if owner is not None:
                message = (
                    "Este CPF/CNPJ é de um cliente que está na Lixeira. Restaure-o por lá."
                    if owner.deleted_at
                    else "Já existe um cliente com este CPF/CNPJ."
                )
                raise serializers.ValidationError({"cpf_cnpj": message})
        return attrs


class ClientFilterSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    tag_id = serializers.UUIDField(required=False, allow_null=True, default=None)
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


class ClientNoteSerializer(serializers.ModelSerializer):
    legal_case_id = TenantScopedPrimaryKeyRelatedField(
        model=LegalCase, source="legal_case", required=False, allow_null=True
    )
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = ClientNote
        fields = ["id", "kind", "body", "legal_case_id", "author_name", "created_at"]
        read_only_fields = ["id", "author_name", "created_at"]
        extra_kwargs = {"body": {"trim_whitespace": True}}

    def get_author_name(self, obj: ClientNote) -> str:
        user = obj.author
        return (user.full_name or user.email) if user else ""


class TimelineItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.CharField()
    at = serializers.DateTimeField()
    title = serializers.CharField()
    body = serializers.CharField()
    meta = serializers.DictField()


class TimelineSerializer(serializers.Serializer):
    results = TimelineItemSerializer(many=True)
    next_before = serializers.DateTimeField(allow_null=True)


class TimelineQuerySerializer(serializers.Serializer):
    before = serializers.DateTimeField(required=False, allow_null=True, default=None)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=30)


class TagSerializer(serializers.ModelSerializer):
    client_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Tag
        fields = ["id", "name", "color", "client_count"]
        read_only_fields = ["id", "client_count"]

    def validate_name(self, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Dê um nome à etiqueta.")
        instance: Tag | None = self.instance
        clash = Tag.objects.filter(name__iexact=value)
        if instance is not None:
            clash = clash.exclude(pk=instance.pk)
        if clash.exists():
            raise serializers.ValidationError("Já existe uma etiqueta com esse nome.")
        return value
