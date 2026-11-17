"""Sinais do app de processos (desacopla de IA/aprovações).

movements_detected(case): andamentos novos ficaram PENDING de aviso. Disparado dentro da
transação; quem agenda trabalho deve usar transaction.on_commit.
"""

from django.dispatch import Signal

movements_detected = Signal()
