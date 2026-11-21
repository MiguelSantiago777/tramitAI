"""Regras dos documentos: validação de arquivo, gravação, consulta por cliente e download."""

import hashlib
import mimetypes
import re
import unicodedata
from pathlib import PurePosixPath
from typing import IO, Any

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.db.models import Q, QuerySet
from rest_framework import status as http_status

from apps.accounts.models import Membership, User
from apps.clientes.models import Client
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.processos.models import LegalCase
from apps.whatsapp.models import Conversation, Message

from .models import Document

# Upload pela equipe: só formatos de documento/mídia comuns. Nada executável, HTML ou SVG.
UPLOAD_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".gif": "image/gif",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".rtf": "application/rtf",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".zip": "application/zip",
}

# Tipos que o navegador pode mostrar na própria página (prévia). O resto sai como download.
INLINE_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "audio/mpeg",
    "audio/ogg",
    "audio/mp4",
    "audio/wav",
    "audio/aac",
    "video/mp4",
    "video/quicktime",
    "video/3gpp",
}

_MAGIC: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG",),
    "image/gif": (b"GIF8",),
}


def safe_filename(name: str, fallback: str = "arquivo") -> str:
    """Nome para exibir/baixar: sem pasta, sem caracteres de controle, tamanho limitado."""
    base = PurePosixPath((name or "").replace("\\", "/")).name
    base = unicodedata.normalize("NFC", base)
    base = re.sub(r"[\x00-\x1f\x7f\"<>|:*?]", "", base).strip(" .")
    if not base:
        base = fallback
    stem, suffix = PurePosixPath(base).stem, PurePosixPath(base).suffix
    return f"{stem[: 200 - len(suffix)]}{suffix}"


def _too_large() -> ApiError:
    mb = settings.DOCUMENT_MAX_BYTES // (1024 * 1024)
    return ApiError(
        f"Arquivo maior que {mb} MB.",
        code="file_too_large",
        status_code=http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    )


def _hash(fp: IO[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: fp.read(1024 * 1024), b""):
        digest.update(chunk)
    fp.seek(0)
    return digest.hexdigest()


def validate_upload(upload: Any) -> tuple[str, str]:
    """Confere tamanho, extensão e assinatura do arquivo. Devolve (nome seguro, content type)."""
    if upload.size > settings.DOCUMENT_MAX_BYTES:
        raise _too_large()
    if upload.size == 0:
        raise ApiError("Arquivo vazio.", code="empty_file")
    name = safe_filename(upload.name)
    content_type = UPLOAD_TYPES.get(PurePosixPath(name).suffix.lower())
    if content_type is None:
        raise ApiError(
            "Formato não aceito. Envie PDF, imagem, áudio, vídeo, Word, Excel ou texto.",
            code="file_type_not_allowed",
        )
    signatures = _MAGIC.get(content_type)
    if signatures:
        head = upload.read(8)
        upload.seek(0)
        if not head.startswith(signatures):
            raise ApiError(
                "O conteúdo do arquivo não confere com a extensão.", code="file_type_mismatch"
            )
    return name, content_type


def can_delete(membership: Membership) -> bool:
    return membership.role in (Membership.Role.OWNER, Membership.Role.LAWYER)


def create_upload(
    *,
    upload: Any,
    user: User,
    client: Client | None = None,
    legal_case: LegalCase | None = None,
    conversation: Conversation | None = None,
    message: Message | None = None,
    category: str = Document.Category.OUTRO,
    description: str = "",
) -> Document:
    if client is None and legal_case is None and conversation is None:
        raise ApiError("Escolha o cliente ou o processo do documento.", code="document_owner")
    name, content_type = validate_upload(upload)
    document = Document(
        name=name,
        content_type=content_type,
        size=upload.size,
        sha256=_hash(upload),
        category=category,
        description=description.strip(),
        source=Document.Source.UPLOAD,
        client=client,
        legal_case=legal_case,
        conversation=conversation,
        message=message,
        uploaded_by=user,
    )
    document.file.save(name, File(upload), save=False)
    document.save()
    audit.record(
        "document.uploaded",
        document,
        actor_type=audit.Actor.USER,
        actor_user=user,
        data={"size": document.size, "content_type": content_type, "category": category},
    )
    return document


def create_from_whatsapp(
    *, message: Message, content: bytes, content_type: str, filename: str
) -> Document:
    """Mídia recebida no WhatsApp vira documento da conversa (e do cliente, se houver)."""
    conversation: Conversation = message.conversation
    content_type = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    guessed = mimetypes.guess_extension(content_type) or ""
    default_name = f"{message.get_type_display()} {message.created_at:%d-%m-%Y %H%M}{guessed}"
    name = safe_filename(filename, fallback=default_name) if filename else default_name
    if not PurePosixPath(name).suffix and guessed:
        name = f"{name}{guessed}"
    document = Document(
        name=name,
        content_type=content_type[:100],
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        category=Document.Category.WHATSAPP,
        description=message.body[:500],
        source=Document.Source.WHATSAPP,
        client=conversation.client,
        conversation=conversation,
        message=message,
    )
    document.file.save(name, ContentFile(content), save=False)
    document.save()
    audit.record(
        "document.received",
        document,
        actor_type=audit.Actor.SYSTEM,
        data={"size": document.size, "content_type": document.content_type},
    )
    return document


def for_client(client: Client) -> QuerySet[Document]:
    """Documentos do cliente: os dele, os dos processos dele e as mídias das conversas dele
    (inclusive as recebidas antes de a conversa ser vinculada ao cliente)."""
    return Document.objects.filter(
        Q(client=client)
        | Q(legal_case__case_clients__client=client)
        | Q(client__isnull=True, conversation__client=client)
    ).distinct()


def delete_document(document: Document, *, user: User, membership: Membership) -> None:
    if not can_delete(membership):
        raise ApiError(
            "Só titular ou advogado(a) pode apagar documentos.",
            code="permission_denied",
            status_code=http_status.HTTP_403_FORBIDDEN,
        )
    audit.record(
        "document.deleted",
        document,
        actor_type=audit.Actor.USER,
        actor_user=user,
        data={"name_len": len(document.name), "size": document.size, "source": document.source},
    )
    document.delete()
