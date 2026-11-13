"""Métriques de supervision : traitement des rêves, appels aux API d'IA, budget.

Calculées à la demande à partir des tables ``Dream`` et ``ApiCall`` : pas
d'infrastructure supplémentaire à héberger pour un projet de cette taille.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.utils import timezone

from dreams.ai.budget import monthly_spend
from dreams.models import ApiCall, ApiService, Dream, Status

# Fenêtres d'observation proposées sur la page de supervision.
WINDOWS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7j": timedelta(days=7),
    "30j": timedelta(days=30),
}


def percentile(values: list[float], rank: float) -> float | None:
    """Percentile par la méthode du rang le plus proche.

    Args:
        values: Valeurs mesurées (non triées).
        rank: Percentile voulu, entre 0 et 100 (ex. 95).

    Returns:
        La valeur du percentile, ou ``None`` s'il n'y a aucune mesure.
    """
    if not values:
        return None
    ordered = sorted(values)
    index = max(int(-(-rank * len(ordered) // 100)) - 1, 0)  # arrondi supérieur
    return ordered[min(index, len(ordered) - 1)]


@dataclass(frozen=True)
class DreamMetrics:
    """Santé du traitement des rêves sur la fenêtre observée."""

    created: int
    completed: int
    failed: int
    in_progress: int
    missing_image: int
    success_rate: float | None
    processing_p50_s: float | None
    processing_p95_s: float | None


@dataclass(frozen=True)
class ServiceMetrics:
    """Performance d'un service d'IA sur la fenêtre observée."""

    service: str
    label: str
    calls: int
    failures: int
    failure_rate: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    cost_usd: Decimal
    fallback_rate: float | None


@dataclass(frozen=True)
class BudgetMetrics:
    """Consommation du budget mensuel d'IA."""

    spent_usd: Decimal
    budget_usd: Decimal
    percent: int
    level: str  # "success", "warning" ou "danger"


def _rate(part: int, total: int) -> float | None:
    return round(100 * part / total, 1) if total else None


def dream_metrics(since: timedelta) -> DreamMetrics:
    """Calcule les métriques de traitement des rêves créés depuis ``since``.

    Args:
        since: Durée de la fenêtre d'observation.

    Returns:
        Volumes par statut, taux de succès et durées de traitement (p50, p95).
    """
    dreams = Dream.objects.filter(created_at__gte=timezone.now() - since)
    counts = dreams.aggregate(
        created=Count("id"),
        completed=Count("id", filter=Q(status=Status.TERMINE)),
        failed=Count("id", filter=Q(status=Status.ECHEC)),
        missing_image=Count("id", filter=Q(status=Status.TERMINE, image="")),
    )
    finished = counts["completed"] + counts["failed"]
    durations = [
        (processed - created).total_seconds()
        for created, processed in dreams.filter(processed_at__isnull=False).values_list(
            "created_at", "processed_at"
        )
    ]
    return DreamMetrics(
        created=counts["created"],
        completed=counts["completed"],
        failed=counts["failed"],
        in_progress=counts["created"] - finished,
        missing_image=counts["missing_image"],
        success_rate=_rate(counts["completed"], finished),
        processing_p50_s=percentile(durations, 50),
        processing_p95_s=percentile(durations, 95),
    )


def service_metrics(since: timedelta) -> list[ServiceMetrics]:
    """Calcule, pour chaque service d'IA, volume, échecs, latence et coût.

    Les appels au lexique local (``provider="local"``) ne comptent pas dans la
    latence et les échecs de l'API, mais donnent le taux de repli de l'émotion.

    Args:
        since: Durée de la fenêtre d'observation.

    Returns:
        Une ligne par service, dans l'ordre du pipeline.
    """
    calls = ApiCall.objects.filter(created_at__gte=timezone.now() - since)
    results = []
    for service in ApiService:
        service_calls = calls.filter(service=service)
        remote = service_calls.exclude(provider="local")
        stats = remote.aggregate(
            calls=Count("id"),
            failures=Count("id", filter=Q(success=False)),
            cost=Sum("cost_usd"),
        )
        latencies = list(remote.filter(success=True).values_list("duration_ms", flat=True))
        fallbacks = service_calls.filter(provider="local").count()
        classified = stats["calls"] - stats["failures"] + fallbacks
        results.append(
            ServiceMetrics(
                service=service.value,
                label=service.label,
                calls=stats["calls"],
                failures=stats["failures"],
                failure_rate=_rate(stats["failures"], stats["calls"]),
                latency_p50_ms=percentile(latencies, 50),
                latency_p95_ms=percentile(latencies, 95),
                cost_usd=stats["cost"] or Decimal("0"),
                fallback_rate=_rate(fallbacks, classified)
                if service == ApiService.EMOTION
                else None,
            )
        )
    return results


def budget_metrics() -> BudgetMetrics:
    """Consommation du budget mensuel, avec un niveau d'alerte.

    Returns:
        Dépense du mois, plafond, pourcentage et couleur d'alerte.
    """
    budget = Decimal(str(settings.AI_MONTHLY_BUDGET_USD))
    spent = monthly_spend()
    percent = int(100 * spent / budget) if budget else 100
    level = "danger" if percent >= 100 else "warning" if percent >= 80 else "success"
    return BudgetMetrics(spent_usd=spent, budget_usd=budget, percent=percent, level=level)


def user_count() -> int:
    """Nombre total de comptes utilisateurs."""
    return get_user_model().objects.count()


def recent_errors(limit: int = 10) -> list[ApiCall]:
    """Derniers appels d'IA en échec, du plus récent au plus ancien."""
    return list(
        ApiCall.objects.filter(success=False)
        .select_related("dream")
        .order_by("-created_at")[:limit]
    )
