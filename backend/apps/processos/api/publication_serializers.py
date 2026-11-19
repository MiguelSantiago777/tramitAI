from typing import Any

from rest_framework import serializers

from apps.core.br import only_digits
from apps.processos.models import UFS, MonitoredOab, Publication

from .serializers import TenantMemberField


class MonitoredOabSerializer(serializers.ModelSerializer):
    # CharField (não ChoiceField): aceita "sp" e normaliza em validate_uf.
    uf = serializers.CharField(max_length=2)
    user_id = TenantMemberField(source="user", required=False, allow_null=True)
    user_name = serializers.SerializerMethodField()
    new_count = serializers.SerializerMethodField()
    total_count = serializers.SerializerMethodField()
    discovering = serializers.SerializerMethodField()

    class Meta:
        model = MonitoredOab
        fields = [
            "id",
            "number",
            "uf",
            "lawyer_name",
            "user_id",
            "user_name",
            "is_active",
            "last_checked_at",
            "fetched_until",
            "last_error",
            "new_count",
            "total_count",
            "discovering",
            "discovered_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "last_checked_at",
            "fetched_until",
            "last_error",
            "discovered_at",
            "created_at",
        ]

    def get_total_count(self, obj: MonitoredOab) -> int:
        annotated = getattr(obj, "publication_count", None)
        return int(annotated) if annotated is not None else 0

    def get_discovering(self, obj: MonitoredOab) -> bool:
        from apps.processos.publications import is_discovering

        return is_discovering(obj)

    def get_user_name(self, obj: MonitoredOab) -> str:
        return (obj.user.full_name or obj.user.email) if obj.user else ""

    def get_new_count(self, obj: MonitoredOab) -> int:
        annotated = getattr(obj, "new_publication_count", None)
        return int(annotated) if annotated is not None else 0

    def validate_number(self, value: str) -> str:
        digits = only_digits(value).lstrip("0")
        if not digits or len(digits) > 8:
            raise serializers.ValidationError("Informe só os números da OAB (ex.: 123456).")
        return digits

    def validate_uf(self, value: str) -> str:
        value = value.strip().upper()
        if value not in UFS:
            raise serializers.ValidationError("UF inválida.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance: MonitoredOab | None = self.instance
        number = attrs.get("number", instance.number if instance else "")
        uf = attrs.get("uf", instance.uf if instance else "")
        clash = MonitoredOab.objects.filter(number=number, uf=uf)
        if instance is not None:
            clash = clash.exclude(pk=instance.pk)
        if clash.exists():
            raise serializers.ValidationError({"number": ["Esta OAB já está cadastrada."]})
        return attrs


class PublicationSerializer(serializers.ModelSerializer):
    cnj_formatted = serializers.CharField(read_only=True)
    case_id = serializers.UUIDField(source="legal_case_id", read_only=True, allow_null=True)
    oab_label = serializers.SerializerMethodField()
    handled_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Publication
        fields = [
            "id",
            "djen_id",
            "cnj_number",
            "cnj_formatted",
            "case_id",
            "tribunal",
            "kind",
            "document_type",
            "orgao",
            "classe",
            "available_on",
            "text",
            "link",
            "recipients",
            "deadline_hints",
            "oab_label",
            "status",
            "handled_at",
            "handled_by_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_oab_label(self, obj: Publication) -> str:
        if obj.oab is None:
            return ""
        label = f"OAB {obj.oab.number}/{obj.oab.uf}"
        return f"{label} · {obj.oab.lawyer_name}" if obj.oab.lawyer_name else label

    def get_handled_by_name(self, obj: Publication) -> str:
        user = obj.handled_by
        return (user.full_name or user.email) if user else ""


class PublicationFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=Publication.Status.choices, required=False, allow_blank=True, default=""
    )
    case_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    q = serializers.CharField(required=False, allow_blank=True, default="")


class PublicationStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Publication.Status.choices)


class FoundCaseSerializer(serializers.Serializer):
    cnj_number = serializers.CharField()
    cnj_formatted = serializers.SerializerMethodField()
    tribunal = serializers.CharField()
    classe = serializers.CharField()
    orgao = serializers.CharField()
    last_on = serializers.DateField()
    count = serializers.IntegerField()
    oab_label = serializers.CharField()

    def get_cnj_formatted(self, obj: Any) -> str:
        from apps.processos.cnj import format_cnj

        return format_cnj(obj.cnj_number)


class ImportCasesSerializer(serializers.Serializer):
    cnj_numbers = serializers.ListField(
        child=serializers.RegexField(r"^\d{20}$"), min_length=1, max_length=500
    )
