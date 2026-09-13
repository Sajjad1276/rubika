from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from .commerce import AdOrder, CommerceService, Payment


@dataclass(frozen=True)
class PaymentRequest:
    payment_id: str
    amount: int
    provider: str
    reference: str


class PaymentProvider(Protocol):
    async def create(self, payment: Payment, order: AdOrder) -> PaymentRequest: ...


class ManualPaymentProvider:
    """Safe default provider until a real gateway is configured."""

    name = "manual"

    async def create(self, payment: Payment, order: AdOrder) -> PaymentRequest:
        reference = payment.provider_reference or f"MAN-{uuid4().hex[:12].upper()}"
        payment.provider_reference = reference
        return PaymentRequest(payment.id, payment.amount, self.name, reference)


async def prepare_payment(db, order: AdOrder, provider: PaymentProvider | None = None) -> PaymentRequest:
    payment = await CommerceService(db).create_payment(order.id)
    gateway = provider or ManualPaymentProvider()
    request = await gateway.create(payment, order)
    await db.flush()
    return request
