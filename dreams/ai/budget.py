"""Plafond de dépenses mensuel sur les API d'IA.

Le sujet impose un budget total ≤ 20 € en production. Chaque appel étant
journalisé avec son coût estimé (``ApiCall``), on peut refuser les nouveaux
traitements avant de dépasser le plafond, au lieu de découvrir la facture.
"""

import logging
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from dreams.ai.errors import AIServiceError
from dreams.models import ApiCall

logger = logging.getLogger(__name__)

# Part du budget à partir de laquelle une alerte est journalisée.
WARNING_RATIO = Decimal("0.8")

BUDGET_EXCEEDED_MESSAGE = (
    "Le service a atteint sa limite d'utilisation pour ce mois-ci. "
    "Merci de réessayer le mois prochain."
)


def monthly_spend() -> Decimal:
    """Coût estimé de tous les appels d'IA depuis le début du mois en cours.

    Returns:
        Le total en dollars US.
    """
    start_of_month = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = ApiCall.objects.filter(created_at__gte=start_of_month).aggregate(total=Sum("cost_usd"))[
        "total"
    ]
    return total or Decimal("0")


def is_budget_exceeded() -> bool:
    """Indique si le plafond mensuel ``AI_MONTHLY_BUDGET_USD`` est atteint.

    Journalise une alerte au-delà de 80 % du plafond.

    Returns:
        ``True`` si plus aucun nouveau traitement ne doit être lancé.
    """
    budget = Decimal(str(settings.AI_MONTHLY_BUDGET_USD))
    spent = monthly_spend()
    if spent >= budget:
        logger.error("Budget IA mensuel atteint : %s $ dépensés sur %s $", spent, budget)
        return True
    if spent >= budget * WARNING_RATIO:
        logger.warning("Budget IA mensuel à plus de 80 %% : %s $ sur %s $", spent, budget)
    return False


def ensure_budget_available() -> None:
    """Vérifie qu'il reste du budget avant un appel payant.

    Raises:
        AIServiceError: Si le plafond mensuel est atteint (non relançable).
    """
    if is_budget_exceeded():
        raise AIServiceError(BUDGET_EXCEEDED_MESSAGE, retryable=False)
