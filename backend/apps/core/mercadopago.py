"""Cliente da API do Mercado Pago (Pix, link de pagamento e assinaturas).

Usado em dois lugares, cada um com o próprio access token:
- financeiro: a conta do ESCRITÓRIO cobra os clientes dele (honorários);
- cobranca: a conta do TRAMITAI cobra a assinatura dos escritórios.

Regras:
- Chamadas HTTP nunca dentro de transação aberta.
- Aviso (webhook) do Mercado Pago não é prova de nada: sempre consultamos o pagamento na API
  com o token da conta antes de dar baixa.
- Nunca logar token nem dados do pagador.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from functools import cache
from typing import Any, Protocol

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)


class MercadoPagoError(Exception):
    def __init__(self, code: str, detail: str = "", *, retryable: bool = False) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail[:255]
        self.retryable = retryable


@dataclass(frozen=True)
class MpAccount:
    user_id: str
    nickname: str


@dataclass(frozen=True)
class Payer:
    email: str
    first_name: str = ""
    last_name: str = ""
    cpf_cnpj: str = ""


@dataclass(frozen=True)
class PixCharge:
    payment_id: str
    status: str
    qr_code: str  # copia e cola
    qr_code_base64: str
    ticket_url: str


@dataclass(frozen=True)
class PaymentLink:
    preference_id: str
    url: str


@dataclass(frozen=True)
class Payment:
    payment_id: str
    status: str  # pending | approved | authorized | in_process | rejected | cancelled | refunded...
    external_reference: str
    amount: Decimal
    date_approved: datetime | None
    payment_type: str  # bank_transfer (pix) | ticket (boleto) | credit_card ...


@dataclass(frozen=True)
class Subscription:
    preapproval_id: str
    status: str  # pending | authorized | paused | cancelled
    external_reference: str
    init_point: str
    next_payment_date: datetime | None


@dataclass(frozen=True)
class AuthorizedPayment:
    """Uma cobrança mensal de assinatura."""

    payment_id: str
    preapproval_id: str
    status: str  # processed | recycling | cancelled | scheduled ...
    amount: Decimal
    date: datetime | None


class MercadoPagoClient(Protocol):
    def whoami(self, token: str) -> MpAccount: ...

    def create_pix(
        self,
        token: str,
        *,
        amount: Decimal,
        description: str,
        payer: Payer,
        external_reference: str,
        notification_url: str,
        expires_at: datetime,
        idempotency_key: str,
    ) -> PixCharge: ...

    def create_link(
        self,
        token: str,
        *,
        title: str,
        amount: Decimal,
        payer: Payer,
        external_reference: str,
        notification_url: str,
        expires_at: datetime,
    ) -> PaymentLink: ...

    def get_payment(self, token: str, payment_id: str) -> Payment: ...

    def cancel_payment(self, token: str, payment_id: str) -> None: ...

    def create_subscription(
        self,
        token: str,
        *,
        reason: str,
        amount: Decimal,
        payer_email: str,
        external_reference: str,
        back_url: str,
        notification_url: str,
    ) -> Subscription: ...

    def get_subscription(self, token: str, preapproval_id: str) -> Subscription: ...

    def cancel_subscription(self, token: str, preapproval_id: str) -> None: ...

    def update_subscription_amount(self, token: str, preapproval_id: str, amount: Decimal) -> None:
        """Troca de plano: a próxima cobrança já vem com o valor novo."""
        ...

    def authorized_payment(self, token: str, payment_id: str) -> AuthorizedPayment: ...

    def authorized_payments_of(self, token: str, preapproval_id: str) -> list[AuthorizedPayment]:
        """Cobranças de uma assinatura (para conferir aviso perdido)."""
        ...


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _dt(value: Any) -> datetime | None:
    return parse_datetime(str(value)) if value else None


def _mp_date(value: datetime) -> str:
    # Formato aceito pelo MP: 2026-11-20T23:59:59.000-03:00
    return value.isoformat(timespec="milliseconds")


class HttpMercadoPagoClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=settings.MERCADOPAGO_API_URL.rstrip("/"),
            timeout=settings.MERCADOPAGO_TIMEOUT,
        )

    def _request(
        self,
        method: str,
        path: str,
        token: str,
        *,
        json: dict[str, Any] | None = None,
        idempotency_key: str = "",
        safe_to_retry: bool = True,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        try:
            response = self._client.request(method, path, json=json, headers=headers)
        except httpx.ConnectError as exc:
            raise MercadoPagoError("connect_error", type(exc).__name__, retryable=True) from exc
        except httpx.HTTPError as exc:
            # Pode ter criado a cobrança. Com chave de idempotência, repetir é seguro.
            raise MercadoPagoError("timeout", type(exc).__name__, retryable=safe_to_retry) from exc

        if response.is_success:
            data = response.json() if response.content else {}
            return data if isinstance(data, dict) else {"results": data}
        try:
            body = response.json()
        except ValueError:
            body = {}
        message = str(body.get("message") or body.get("error") or response.reason_phrase)
        logger.warning("mercadopago %s %s → %s", method, path.split("?")[0], response.status_code)
        if response.status_code == 401:
            raise MercadoPagoError("invalid_token", "Access token inválido ou revogado.")
        if response.status_code == 404:
            raise MercadoPagoError("not_found", message)
        retryable = response.status_code == 429 or response.status_code >= 500
        raise MercadoPagoError(f"http_{response.status_code}", message, retryable=retryable)

    def whoami(self, token: str) -> MpAccount:
        data = self._request("GET", "/users/me", token)
        return MpAccount(user_id=str(data.get("id", "")), nickname=str(data.get("nickname", "")))

    def create_pix(
        self,
        token: str,
        *,
        amount: Decimal,
        description: str,
        payer: Payer,
        external_reference: str,
        notification_url: str,
        expires_at: datetime,
        idempotency_key: str,
    ) -> PixCharge:
        body: dict[str, Any] = {
            "transaction_amount": _money(amount),
            "description": description[:250],
            "payment_method_id": "pix",
            "external_reference": external_reference,
            "date_of_expiration": _mp_date(expires_at),
            "payer": _payer(payer),
        }
        if notification_url:
            body["notification_url"] = notification_url
        data = self._request(
            "POST", "/v1/payments", token, json=body, idempotency_key=idempotency_key
        )
        tx = (data.get("point_of_interaction") or {}).get("transaction_data") or {}
        return PixCharge(
            payment_id=str(data.get("id", "")),
            status=str(data.get("status", "")),
            qr_code=str(tx.get("qr_code", "")),
            qr_code_base64=str(tx.get("qr_code_base64", "")),
            ticket_url=str(tx.get("ticket_url", "")),
        )

    def create_link(
        self,
        token: str,
        *,
        title: str,
        amount: Decimal,
        payer: Payer,
        external_reference: str,
        notification_url: str,
        expires_at: datetime,
    ) -> PaymentLink:
        body: dict[str, Any] = {
            "items": [
                {
                    "title": title[:250],
                    "quantity": 1,
                    "currency_id": "BRL",
                    "unit_price": _money(amount),
                }
            ],
            "payer": {"email": payer.email, "name": payer.first_name, "surname": payer.last_name},
            "external_reference": external_reference,
            "expires": True,
            "expiration_date_to": _mp_date(expires_at),
            "statement_descriptor": settings.MERCADOPAGO_STATEMENT[:22],
        }
        if notification_url:
            body["notification_url"] = notification_url
        data = self._request("POST", "/checkout/preferences", token, json=body)
        return PaymentLink(
            preference_id=str(data.get("id", "")), url=str(data.get("init_point", ""))
        )

    def get_payment(self, token: str, payment_id: str) -> Payment:
        data = self._request("GET", f"/v1/payments/{payment_id}", token)
        return Payment(
            payment_id=str(data.get("id", payment_id)),
            status=str(data.get("status", "")),
            external_reference=str(data.get("external_reference") or ""),
            amount=Decimal(str(data.get("transaction_amount") or "0")),
            date_approved=_dt(data.get("date_approved")),
            payment_type=str(data.get("payment_type_id", "")),
        )

    def cancel_payment(self, token: str, payment_id: str) -> None:
        self._request("PUT", f"/v1/payments/{payment_id}", token, json={"status": "cancelled"})

    def create_subscription(
        self,
        token: str,
        *,
        reason: str,
        amount: Decimal,
        payer_email: str,
        external_reference: str,
        back_url: str,
        notification_url: str,
    ) -> Subscription:
        body: dict[str, Any] = {
            "reason": reason[:250],
            "external_reference": external_reference,
            "payer_email": payer_email,
            "back_url": back_url,
            "status": "pending",
            "auto_recurring": {
                "frequency": 1,
                "frequency_type": "months",
                "transaction_amount": _money(amount),
                "currency_id": "BRL",
            },
        }
        if notification_url:
            body["notification_url"] = notification_url
        return _subscription(self._request("POST", "/preapproval", token, json=body))

    def get_subscription(self, token: str, preapproval_id: str) -> Subscription:
        return _subscription(self._request("GET", f"/preapproval/{preapproval_id}", token))

    def cancel_subscription(self, token: str, preapproval_id: str) -> None:
        self._request("PUT", f"/preapproval/{preapproval_id}", token, json={"status": "cancelled"})

    def update_subscription_amount(self, token: str, preapproval_id: str, amount: Decimal) -> None:
        self._request(
            "PUT",
            f"/preapproval/{preapproval_id}",
            token,
            json={"auto_recurring": {"transaction_amount": _money(amount), "currency_id": "BRL"}},
        )

    def authorized_payment(self, token: str, payment_id: str) -> AuthorizedPayment:
        return _authorized(self._request("GET", f"/authorized_payments/{payment_id}", token))

    def authorized_payments_of(self, token: str, preapproval_id: str) -> list[AuthorizedPayment]:
        data = self._request(
            "GET", f"/authorized_payments/search?preapproval_id={preapproval_id}", token
        )
        return [_authorized(item) for item in data.get("results", []) if isinstance(item, dict)]


def _payer(payer: Payer) -> dict[str, Any]:
    data: dict[str, Any] = {"email": payer.email}
    if payer.first_name:
        data["first_name"] = payer.first_name
    if payer.last_name:
        data["last_name"] = payer.last_name
    digits = "".join(c for c in payer.cpf_cnpj if c.isalnum())
    if len(digits) in (11, 14):
        data["identification"] = {"type": "CPF" if len(digits) == 11 else "CNPJ", "number": digits}
    return data


def _authorized(data: dict[str, Any]) -> AuthorizedPayment:
    raw_payment = data.get("payment")
    payment: dict[str, Any] = raw_payment if isinstance(raw_payment, dict) else {}
    return AuthorizedPayment(
        payment_id=str(data.get("id", "")),
        preapproval_id=str(data.get("preapproval_id") or ""),
        status=str(data.get("status") or payment.get("status") or ""),
        amount=Decimal(str(data.get("transaction_amount") or "0")),
        date=_dt(data.get("date_created") or data.get("debit_date")),
    )


def _subscription(data: dict[str, Any]) -> Subscription:
    return Subscription(
        preapproval_id=str(data.get("id", "")),
        status=str(data.get("status", "")),
        external_reference=str(data.get("external_reference") or ""),
        init_point=str(data.get("init_point", "")),
        next_payment_date=_dt(data.get("next_payment_date")),
    )


# ---------------------------------------------------------------- fake (dev e testes)


@dataclass
class FakeMercadoPago:
    """Não sai da máquina. Os testes mudam `payments`/`subscriptions` para simular o MP."""

    valid_tokens: set[str] = field(default_factory=lambda: {"APP_USR-teste"})
    payments: dict[str, Payment] = field(default_factory=dict)
    subscriptions: dict[str, Subscription] = field(default_factory=dict)
    created: list[dict[str, Any]] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    authorized: dict[str, AuthorizedPayment] = field(default_factory=dict)
    amount_updates: list[tuple[str, Decimal]] = field(default_factory=list)
    fail_next: MercadoPagoError | None = None

    def _check(self, token: str) -> None:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        if token not in self.valid_tokens:
            raise MercadoPagoError("invalid_token", "Access token inválido ou revogado.")

    def whoami(self, token: str) -> MpAccount:
        self._check(token)
        return MpAccount(user_id="123456", nickname="ESCRITORIO_TESTE")

    def create_pix(self, token: str, **kwargs: Any) -> PixCharge:
        self._check(token)
        payment_id = str(1000 + len(self.payments))
        self.created.append({"kind": "pix", "payment_id": payment_id, **kwargs})
        self.payments[payment_id] = Payment(
            payment_id=payment_id,
            status="pending",
            external_reference=kwargs["external_reference"],
            amount=kwargs["amount"],
            date_approved=None,
            payment_type="bank_transfer",
        )
        return PixCharge(
            payment_id=payment_id,
            status="pending",
            qr_code=f"00020126580014br.gov.bcb.pix0136fake-{payment_id}",
            qr_code_base64="iVBORw0KGgo=",
            ticket_url=f"https://www.mercadopago.com.br/payments/{payment_id}/ticket",
        )

    def create_link(self, token: str, **kwargs: Any) -> PaymentLink:
        self._check(token)
        pref = f"pref-{uuid.uuid4().hex[:8]}"
        self.created.append({"kind": "link", "preference_id": pref, **kwargs})
        return PaymentLink(preference_id=pref, url=f"https://mpago.la/{pref}")

    def get_payment(self, token: str, payment_id: str) -> Payment:
        self._check(token)
        if payment_id not in self.payments:
            raise MercadoPagoError("not_found", "pagamento não existe")
        return self.payments[payment_id]

    def cancel_payment(self, token: str, payment_id: str) -> None:
        self._check(token)
        self.cancelled.append(payment_id)

    def create_subscription(self, token: str, **kwargs: Any) -> Subscription:
        self._check(token)
        sub_id = f"preapp-{uuid.uuid4().hex[:8]}"
        self.created.append({"kind": "subscription", "preapproval_id": sub_id, **kwargs})
        sub = Subscription(
            preapproval_id=sub_id,
            status="pending",
            external_reference=kwargs["external_reference"],
            init_point=f"https://www.mercadopago.com.br/subscriptions/checkout?preapproval_id={sub_id}",
            next_payment_date=None,
        )
        self.subscriptions[sub_id] = sub
        return sub

    def get_subscription(self, token: str, preapproval_id: str) -> Subscription:
        self._check(token)
        if preapproval_id not in self.subscriptions:
            raise MercadoPagoError("not_found", "assinatura não existe")
        return self.subscriptions[preapproval_id]

    def cancel_subscription(self, token: str, preapproval_id: str) -> None:
        self._check(token)
        self.cancelled.append(preapproval_id)
        sub = self.subscriptions.get(preapproval_id)
        if sub is not None:
            self.subscriptions[preapproval_id] = Subscription(
                preapproval_id=sub.preapproval_id,
                status="cancelled",
                external_reference=sub.external_reference,
                init_point=sub.init_point,
                next_payment_date=sub.next_payment_date,
            )

    def update_subscription_amount(self, token: str, preapproval_id: str, amount: Decimal) -> None:
        self._check(token)
        self.amount_updates.append((preapproval_id, amount))

    def authorized_payment(self, token: str, payment_id: str) -> AuthorizedPayment:
        self._check(token)
        if payment_id not in self.authorized:
            raise MercadoPagoError("not_found", "cobrança não existe")
        return self.authorized[payment_id]

    def authorized_payments_of(self, token: str, preapproval_id: str) -> list[AuthorizedPayment]:
        self._check(token)
        return [a for a in self.authorized.values() if a.preapproval_id == preapproval_id]


@cache
def _fake() -> FakeMercadoPago:
    return FakeMercadoPago()


def get_mercadopago() -> MercadoPagoClient:
    name = settings.MERCADOPAGO_CLIENT
    if name == "fake":
        return _fake()
    if name == "http":
        return HttpMercadoPagoClient()
    raise ImproperlyConfigured(f"cliente do Mercado Pago desconhecido: {name}")


def public_url(path: str) -> str:
    """URL pública para o MP chamar de volta. Fora de HTTPS (dev), o MP recusa: devolve ''."""
    base = settings.PUBLIC_API_URL.rstrip("/")
    return f"{base}{path}" if base.startswith("https://") else ""
