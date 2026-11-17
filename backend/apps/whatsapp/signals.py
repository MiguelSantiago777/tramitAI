"""Sinais do WhatsApp. Outros apps (ia, aprovacoes) reagem sem o whatsapp depender deles.

Todos são enviados dentro da transação e com o tenant ativo; receptores que agendam tasks
devem usar transaction.on_commit.
"""

from django.dispatch import Signal

# kwargs: message (Message recebida, nova), conversation
inbound_message_received = Signal()

# kwargs: message (Message de saída já atualizada para SENT ou FAILED)
outbound_message_settled = Signal()
