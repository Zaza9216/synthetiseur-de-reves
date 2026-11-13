"""Tests du tableau de bord : filtres, statistiques, graphique et données de démo."""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from dreams.forms import DreamFilterForm
from dreams.models import EMOTION_STYLES, Dream, Emotion
from dreams.stats import (
    DEFAULT_PERIOD_DAYS,
    compute_dashboard_stats,
    emotion_distribution,
    emotion_timeline,
    resolve_period,
)

MakeDream = Callable[..., Dream]


def dated(make_dream: MakeDream, user: Any, day: date, **fields: Any) -> Dream:
    """Crée un rêve à une date donnée (midi, heure locale)."""
    dream = make_dream(user, **fields)
    moment = timezone.make_aware(datetime(day.year, day.month, day.day, 12, 0))
    Dream.objects.filter(pk=dream.pk).update(created_at=moment)
    dream.refresh_from_db()
    return dream


# --- Période et formulaire -----------------------------------------------------------


def test_resolve_period_defaults_to_last_12_weeks() -> None:
    start, end = resolve_period(None, None)

    assert end == timezone.localdate()
    assert (end - start).days == DEFAULT_PERIOD_DAYS - 1


def test_resolve_period_keeps_given_dates() -> None:
    assert resolve_period(date(2026, 1, 1), date(2026, 2, 1)) == (
        date(2026, 1, 1),
        date(2026, 2, 1),
    )
    assert resolve_period(None, date(2026, 6, 30))[0] == date(2026, 6, 30) - timedelta(
        days=DEFAULT_PERIOD_DAYS - 1
    )


def test_filter_form_rejects_inverted_period() -> None:
    form = DreamFilterForm({"start": "2026-05-10", "end": "2026-05-01"})

    assert not form.is_valid()
    assert "précéder" in form.non_field_errors()[0]


def test_filter_form_rejects_unknown_emotion() -> None:
    assert not DreamFilterForm({"emotion": "euphorique"}).is_valid()


# --- Statistiques ----------------------------------------------------------------------


def test_distribution_sorted_with_percentages(user: Any, make_dream: MakeDream) -> None:
    for emotion in ["heureux", "heureux", "heureux", "stressant", ""]:
        make_dream(user, emotion=emotion)

    shares = emotion_distribution(Dream.objects.all())

    assert [(s.emotion, s.count, s.percent) for s in shares] == [
        ("heureux", 3, 75),
        ("stressant", 1, 25),
    ]
    assert shares[0].hex == EMOTION_STYLES[Emotion.HEUREUX].hex
    assert shares[0].label == "Heureux"


def test_weekly_timeline_fills_empty_weeks(user: Any, make_dream: MakeDream) -> None:
    monday = date(2026, 10, 5)  # un lundi
    dated(make_dream, user, monday, emotion="heureux")
    dated(make_dream, user, monday + timedelta(days=2), emotion="heureux")
    dated(make_dream, user, monday + timedelta(days=14), emotion="triste")

    timeline = emotion_timeline(Dream.objects.all(), monday, monday + timedelta(days=20))

    assert timeline["granularity"] == "semaine"
    assert len(timeline["labels"]) == 3
    by_emotion = {d["emotion"]: d["data"] for d in timeline["datasets"]}
    assert by_emotion == {"heureux": [2, 0, 0], "triste": [0, 0, 1]}


def test_long_period_is_grouped_by_month(user: Any, make_dream: MakeDream) -> None:
    dated(make_dream, user, date(2026, 1, 15), emotion="neutre")
    dated(make_dream, user, date(2026, 8, 3), emotion="neutre")

    timeline = emotion_timeline(Dream.objects.all(), date(2026, 1, 1), date(2026, 8, 31))

    assert timeline["granularity"] == "mois"
    assert timeline["labels"][0] == "janvier 2026"
    assert len(timeline["labels"]) == 8
    assert timeline["datasets"][0]["data"] == [1, 0, 0, 0, 0, 0, 0, 1]


def test_month_buckets_cross_year_boundary(user: Any, make_dream: MakeDream) -> None:
    timeline = emotion_timeline(Dream.objects.all(), date(2025, 11, 1), date(2026, 6, 1))

    assert timeline["labels"][:3] == ["novembre 2025", "décembre 2025", "janvier 2026"]


def test_dashboard_stats(user: Any, make_dream: MakeDream) -> None:
    start, end = date(2026, 10, 1), date(2026, 10, 14)
    for _ in range(3):
        dated(make_dream, user, date(2026, 10, 2), emotion="stressant")
    dated(make_dream, user, date(2026, 10, 3), emotion="heureux")
    dated(make_dream, user, date(2026, 10, 4), emotion="", status="transcription")

    stats = compute_dashboard_stats(Dream.objects.all(), start, end)

    assert stats.total == 5
    assert stats.analysed == 4
    assert stats.dominant.emotion == "stressant"
    assert stats.dominant.percent == 75
    assert stats.per_week == 2.5


@pytest.mark.django_db
def test_dashboard_stats_without_dreams() -> None:
    stats = compute_dashboard_stats(Dream.objects.none(), date(2026, 1, 1), date(2026, 1, 7))

    assert (stats.total, stats.analysed, stats.dominant, stats.per_week) == (0, 0, None, 0)


# --- Page -----------------------------------------------------------------------------


def test_dashboard_shows_stats_chart_and_dreams(
    client: Client, user: Any, make_dream: MakeDream
) -> None:
    make_dream(user, emotion="heureux")
    make_dream(user, emotion="heureux")
    make_dream(user, emotion="triste")
    client.force_login(user)

    response = client.get(reverse("dreams:list"))
    html = response.content.decode()

    assert response.context["stats"].total == 3
    assert response.context["stats"].dominant.emotion == "heureux"
    assert 'id="timeline-chart"' in html
    assert 'id="timeline-data"' in html
    assert "chart.umd.min.js" in html
    assert "js/dashboard.js" in html


def test_dashboard_filters_by_period(client: Client, user: Any, make_dream: MakeDream) -> None:
    old = dated(make_dream, user, date(2026, 3, 10), transcription="Rêve de mars")
    dated(make_dream, user, date(2026, 6, 10), transcription="Rêve de juin")
    client.force_login(user)

    response = client.get(reverse("dreams:list"), {"start": "2026-03-01", "end": "2026-03-31"})

    assert list(response.context["dreams"]) == [old]
    assert response.context["stats"].total == 1


def test_dashboard_filters_by_emotion_but_keeps_period_stats(
    client: Client, user: Any, make_dream: MakeDream
) -> None:
    sad = make_dream(user, emotion="triste")
    make_dream(user, emotion="heureux")
    client.force_login(user)

    response = client.get(reverse("dreams:list"), {"emotion": "triste"})

    assert list(response.context["dreams"]) == [sad]
    assert response.context["stats"].total == 2
    assert "Rêves « triste »" in response.content.decode()


def test_invalid_filters_are_reported_and_ignored(
    client: Client, user: Any, make_dream: MakeDream
) -> None:
    make_dream(user)
    client.force_login(user)

    response = client.get(reverse("dreams:list"), {"start": "2026-05-10", "end": "2026-05-01"})

    assert "précéder" in response.content.decode()
    assert len(response.context["dreams"]) == 1


def test_no_matching_dream_message(client: Client, user: Any, make_dream: MakeDream) -> None:
    make_dream(user, emotion="heureux")
    client.force_login(user)

    response = client.get(reverse("dreams:list"), {"emotion": "colere"})

    assert "Aucun rêve ne correspond à ces filtres." in response.content.decode()


def test_pagination_keeps_filters(client: Client, user: Any, make_dream: MakeDream) -> None:
    for _ in range(10):
        make_dream(user, emotion="heureux")
    client.force_login(user)

    html = client.get(reverse("dreams:list"), {"emotion": "heureux"}).content.decode()

    assert "?emotion=heureux&amp;page=2" in html


def test_dashboard_stats_ignore_other_users(
    client: Client, user: Any, other_user: Any, make_dream: MakeDream
) -> None:
    make_dream(user, emotion="heureux")
    make_dream(other_user, emotion="stressant")
    make_dream(other_user, emotion="stressant")
    client.force_login(user)

    stats = client.get(reverse("dreams:list")).context["stats"]

    assert stats.total == 1
    assert stats.dominant.emotion == "heureux"


def test_no_chart_without_analysed_dream(client: Client, user: Any, make_dream: MakeDream) -> None:
    make_dream(user, emotion="", status="transcription")
    client.force_login(user)

    html = client.get(reverse("dreams:list")).content.decode()

    assert "Pas encore de rêve analysé" in html
    assert "chart.umd.min.js" not in html


# --- Données de démonstration -----------------------------------------------------------


@pytest.mark.django_db
def test_seed_demo_dreams_creates_user_and_dreams() -> None:
    call_command("seed_demo_dreams", "--username", "demo", "--count", "25", "--seed", "1")

    dreams = Dream.objects.filter(user__username="demo")
    assert dreams.count() == 25
    assert dreams.filter(status="termine").count() == 25
    oldest = dreams.order_by("created_at").first().created_at
    assert oldest >= timezone.now() - timedelta(weeks=12, minutes=1)
    assert len(set(dreams.values_list("emotion", flat=True))) > 1


@pytest.mark.django_db
def test_seed_demo_dreams_clear_option() -> None:
    call_command("seed_demo_dreams", "--count", "5", "--seed", "1")
    call_command("seed_demo_dreams", "--count", "3", "--seed", "2", "--clear")

    assert Dream.objects.count() == 3
