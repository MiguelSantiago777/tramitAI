"""Sinais do app de processos (desacopla de IA/aprovações).

movements_detected(case): andamentos novos ficaram PENDING de aviso. Disparado dentro da
transação; quem agenda trabalho deve usar transaction.on_commit.

publications_detected(publications): publicações novas e recentes do Diário (DJEN), também
dentro da transação.
"""

from django.dispatch import Signal

movements_detected = Signal()
publications_detected = Signal()
