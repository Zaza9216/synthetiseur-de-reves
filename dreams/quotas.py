"""Quotas d'utilisation : limitent le nombre de rêves pour maîtriser le budget API."""

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from dreams.models import Dream


def dreams_created_today(user: AbstractBaseUser) -> int:
    """Compte les rêves créés par l'utilisateur depuis minuit (heure locale).

    Args:
        user: L'utilisateur concerné.

    Returns:
        Le nombre de rêves créés aujourd'hui.
    """
    start_of_day = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return Dream.objects.filter(user=user, created_at__gte=start_of_day).count()


def dreams_left_today(user: AbstractBaseUser) -> int:
    """Nombre de rêves que l'utilisateur peut encore créer aujourd'hui.

    Args:
        user: L'utilisateur concerné.

    Returns:
        Le nombre de rêves restants, jamais négatif.
    """
    return max(settings.DREAM_DAILY_LIMIT - dreams_created_today(user), 0)
