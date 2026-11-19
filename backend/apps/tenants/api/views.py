from typing import cast

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import team
from apps.accounts.models import Membership, User
from apps.accounts.permissions import IsOwnerForWrites
from apps.accounts.selectors import tenant_members
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.core.tenancy import get_current_tenant_id
from apps.tenants import services
from apps.tenants.models import ClientTermVersion, Tenant, TenantSettings

from .serializers import (
    ClientTermVersionSerializer,
    InviteSerializer,
    MemberSerializer,
    MemberUpdateSerializer,
    TeamMemberSerializer,
    TenantSettingsSerializer,
)


class TenantSettingsView(APIView):
    """Configurações do escritório. Alterar: só o titular."""

    permission_classes = [IsOwnerForWrites]

    @extend_schema(responses=TenantSettingsSerializer, tags=["tenant"])
    def get(self, request: Request) -> Response:
        settings = get_object_or_404(TenantSettings.objects.all())
        return Response(TenantSettingsSerializer(settings).data)

    @extend_schema(
        request=TenantSettingsSerializer, responses=TenantSettingsSerializer, tags=["tenant"]
    )
    def patch(self, request: Request) -> Response:
        settings = get_object_or_404(TenantSettings.objects.all())
        payload = TenantSettingsSerializer(settings, data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        changed = sorted(data)
        name = data.pop("tenant_name", None)
        if name is not None:
            Tenant.objects.filter(pk=settings.tenant_id).update(name=name)
        for field, value in data.items():
            setattr(settings, field, value)
        settings.save()
        audit.record(
            "settings.updated",
            settings,
            actor_type=audit.Actor.USER,
            actor_user=request.user,
            data={"fields": changed},
        )
        return Response(TenantSettingsSerializer(settings).data)


class MembersView(APIView):
    @extend_schema(responses=MemberSerializer(many=True), tags=["tenant"])
    def get(self, request: Request) -> Response:
        members = tenant_members(tenant_id=get_current_tenant_id())
        return Response(MemberSerializer(members, many=True).data)


class ClientTermView(APIView):
    """Termo de ciência de IA vigente. Publicar nova versão: só o titular."""

    permission_classes = [IsOwnerForWrites]

    @extend_schema(responses=ClientTermVersionSerializer, tags=["tenant"])
    def get(self, request: Request) -> Response:
        term = services.active_term_version()
        if term is None:
            raise ApiError(
                "Nenhum termo publicado.",
                code="no_active_term",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return Response(ClientTermVersionSerializer(term).data)

    @extend_schema(
        request=ClientTermVersionSerializer,
        responses={201: ClientTermVersionSerializer},
        tags=["tenant"],
    )
    def post(self, request: Request) -> Response:
        payload = ClientTermVersionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        term = services.publish_term_version(
            body=payload.validated_data["body"],
            created_by=request.user,  # type: ignore[arg-type]
        )
        return Response(ClientTermVersionSerializer(term).data, status=status.HTTP_201_CREATED)


class ClientTermVersionsView(APIView):
    @extend_schema(responses=ClientTermVersionSerializer(many=True), tags=["tenant"])
    def get(self, request: Request) -> Response:
        versions = ClientTermVersion.objects.select_related("created_by").order_by("-version")
        return Response(ClientTermVersionSerializer(versions, many=True).data)


class TeamView(APIView):
    """Equipe completa (inclui inativos e convites pendentes). Convidar: só o titular."""

    permission_classes = [IsOwnerForWrites]

    @extend_schema(responses=TeamMemberSerializer(many=True), tags=["tenant"])
    def get(self, request: Request) -> Response:
        members = team.team(get_current_tenant_id())
        data = TeamMemberSerializer(members, many=True, context={"request": request}).data
        return Response(data)

    @extend_schema(request=InviteSerializer, responses=TeamMemberSerializer, tags=["tenant"])
    def post(self, request: Request) -> Response:
        payload = InviteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        membership = team.invite_member(
            tenant_id=get_current_tenant_id(),
            invited_by=cast(User, request.user),
            **payload.validated_data,
        )
        audit.record(
            "team.invited",
            membership,
            actor_type=audit.Actor.USER,
            actor_user=request.user,
            data={"role": membership.role},
        )
        member = team.TeamMember(membership, pending=not membership.user.has_usable_password())
        data = dict(TeamMemberSerializer(member, context={"request": request}).data)
        # Sem e-mail configurado, o titular manda este link (WhatsApp, por exemplo).
        data["access_link"] = team.access_link(membership).url if member.pending else ""
        return Response(data, status=status.HTTP_201_CREATED)


class TeamMemberView(APIView):
    permission_classes = [IsOwnerForWrites]

    def _membership(self, membership_id: str) -> Membership:
        return get_object_or_404(
            Membership.objects.select_related("user"),
            pk=membership_id,
            tenant_id=get_current_tenant_id(),
        )

    @extend_schema(request=MemberUpdateSerializer, responses=TeamMemberSerializer, tags=["tenant"])
    def patch(self, request: Request, membership_id: str) -> Response:
        payload = MemberUpdateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        membership = team.update_member(
            self._membership(membership_id),
            actor=cast(User, request.user),
            role=payload.validated_data.get("role"),
            is_active=payload.validated_data.get("is_active"),
        )
        audit.record(
            "team.updated",
            membership,
            actor_type=audit.Actor.USER,
            actor_user=request.user,
            data={"role": membership.role, "is_active": membership.is_active},
        )
        member = team.TeamMember(membership, pending=not membership.user.has_usable_password())
        return Response(TeamMemberSerializer(member, context={"request": request}).data)


class TeamResendInviteView(TeamMemberView):
    @extend_schema(request=None, responses={204: None}, tags=["tenant"])
    def post(self, request: Request, membership_id: str) -> Response:
        team.resend_invite(self._membership(membership_id), invited_by=cast(User, request.user))
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeamAccessLinkView(TeamMemberView):
    @extend_schema(
        request=None,
        responses=inline_serializer(
            "TeamAccessLink",
            {"url": serializers.CharField(), "kind": serializers.CharField()},
        ),
        tags=["tenant"],
    )
    def post(self, request: Request, membership_id: str) -> Response:
        """Link para entrar: convite (ainda sem senha) ou nova senha. Vale 3 dias, uso único."""
        membership = self._membership(membership_id)
        link = team.access_link(membership)
        audit.record(
            "team.access_link_created",
            membership,
            actor_type=audit.Actor.USER,
            actor_user=request.user,
            data={"kind": link.kind},
        )
        return Response({"url": link.url, "kind": link.kind})
