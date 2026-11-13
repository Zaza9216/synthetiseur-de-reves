"""Statistiques du tableau de bord : fréquence des rêves et évolution des émotions.

Toutes les agrégations sont faites par la base de données (``COUNT`` et
``GROUP BY``) : le coût ne dépend pas du nombre de rêves chargés en mémoire.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from django.db.models import Count, QuerySet
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone
from django.utils.formats import date_format

from dreams.models import EMOTION_STYLES, Dream, Emotion

# Au-delà de cette durée, l'évolution est regroupée par mois plutôt que par semaine.
MONTHLY_THRESHOLD_DAYS = 182
# Période affichée par défaut quand aucune date n'est choisie (12 semaines).
DEFAULT_PERIOD_DAYS = 12 * 7


@dataclass(frozen=True)
class EmotionShare:
    """Part d'une émotion dans les rêves de la période."""

    emotion: str
    label: str
    icon: str
    color: str
    hex: str
    count: int
    percent: int


@dataclass
class DashboardStats:
    """Chiffres et séries affichés sur le tableau de bord."""

    total: int
    analysed: int
    dominant: EmotionShare | None
    per_week: float
    distribution: list[EmotionShare]
    timeline: dict[str, Any] = field(default_factory=dict)


def resolve_period(start: date | None, end: date | None) -> tuple[date, date]:
    """Complète une période partiellement renseignée.

    Args:
        start: Date de début choisie, ou ``None``.
        end: Date de fin choisie, ou ``None``.

    Returns:
        La période effective ``(début, fin)`` : fin par défaut aujourd'hui,
        début par défaut 12 semaines avant la fin.
    """
    end = end or timezone.localdate()
    start = start or end - timedelta(days=DEFAULT_PERIOD_DAYS - 1)
    return start, end


def _bucket_starts(start: date, end: date, monthly: bool) -> list[date]:
    """Liste les débuts de chaque semaine (lundi) ou mois couvrant la période."""
    buckets = []
    if monthly:
        current = start.replace(day=1)
        while current <= end:
            buckets.append(current)
            current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    else:
        current = start - timedelta(days=start.weekday())
        while current <= end:
            buckets.append(current)
            current += timedelta(days=7)
    return buckets


def _bucket_label(bucket: date, monthly: bool) -> str:
    return date_format(bucket, "F Y" if monthly else "j b")


def emotion_distribution(dreams: QuerySet[Dream]) -> list[EmotionShare]:
    """Répartition des émotions, de la plus fréquente à la moins fréquente.

    Args:
        dreams: Les rêves à analyser (les rêves sans émotion sont ignorés).

    Returns:
        Une part par émotion présente, avec effectif et pourcentage arrondi.
    """
    rows = (
        dreams.exclude(emotion="")
        .values("emotion")
        .annotate(count=Count("id"))
        .order_by("-count", "emotion")
    )
    total = sum(row["count"] for row in rows)
    shares = []
    for row in rows:
        style = EMOTION_STYLES[row["emotion"]]
        shares.append(
            EmotionShare(
                emotion=row["emotion"],
                label=Emotion(row["emotion"]).label,
                icon=style.icon,
                color=style.color,
                hex=style.hex,
                count=row["count"],
                percent=round(100 * row["count"] / total),
            )
        )
    return shares


def emotion_timeline(dreams: QuerySet[Dream], start: date, end: date) -> dict[str, Any]:
    """Nombre de rêves par période et par émotion, prêt pour un graphique empilé.

    Args:
        dreams: Les rêves de la période.
        start: Début de la période.
        end: Fin de la période.

    Returns:
        ``{"granularity": "semaine" | "mois", "labels": [...], "datasets": [...]}``
        avec un jeu de données par émotion, complété par des zéros.
    """
    monthly = (end - start).days > MONTHLY_THRESHOLD_DAYS
    trunc = TruncMonth("created_at") if monthly else TruncWeek("created_at")
    rows = (
        dreams.exclude(emotion="")
        .annotate(bucket=trunc)
        .values("bucket", "emotion")
        .annotate(count=Count("id"))
    )
    counts: dict[tuple[date, str], int] = {}
    for row in rows:
        bucket = row["bucket"]
        bucket_date = timezone.localtime(bucket).date() if hasattr(bucket, "hour") else bucket
        counts[(bucket_date, row["emotion"])] = row["count"]

    buckets = _bucket_starts(start, end, monthly)
    datasets = []
    for emotion in Emotion:
        data = [counts.get((bucket, emotion.value), 0) for bucket in buckets]
        if any(data):
            datasets.append(
                {
                    "emotion": emotion.value,
                    "label": emotion.label,
                    "color": EMOTION_STYLES[emotion].hex,
                    "data": data,
                }
            )
    return {
        "granularity": "mois" if monthly else "semaine",
        "labels": [_bucket_label(bucket, monthly) for bucket in buckets],
        "datasets": datasets,
    }


def compute_dashboard_stats(dreams: QuerySet[Dream], start: date, end: date) -> DashboardStats:
    """Calcule toutes les statistiques du tableau de bord pour une période.

    Args:
        dreams: Les rêves de l'utilisateur, déjà filtrés sur la période.
        start: Début de la période.
        end: Fin de la période.

    Returns:
        Les statistiques à afficher.
    """
    distribution = emotion_distribution(dreams)
    total = dreams.count()
    weeks = max((end - start).days + 1, 1) / 7
    return DashboardStats(
        total=total,
        analysed=sum(share.count for share in distribution),
        dominant=distribution[0] if distribution else None,
        per_week=round(total / weeks, 1),
        distribution=distribution,
        timeline=emotion_timeline(dreams, start, end),
    )
