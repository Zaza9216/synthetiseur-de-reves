"""Tests de la supervision : métriques, page réservée, logs, middlewares."""

import json
import logging
import sys
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from pytest_django.fixtures import Settings

from core import metrics
from core.logging import JsonFormatter
from core.middleware import RequestTimingMiddleware
from dreams.models import ApiCall, ApiService, Dream, Status

MakeDream = Callable[..., Dream]


def call(service: str, success: bool = True, ms: int = 100, cost: str = "0", **kw: Any) -> ApiCall:
    """Enregistre un appel d'API fictif."""
    return ApiCall.objects.create(
        service=service,
        model_name=kw.pop("model_name", "m"),
        success=success,
        duration_ms=ms,
        cost_usd=Decimal(cost),
        error_type="" if success else "APITimeoutError",
        **kw,
    )


@pytest.fixture
def staff(db: None) -> Any:
    """Administrateur de l'application."""
    return get_user_model().objects.create_user(
        "admin", "admin@example.com", "x-Admin-2026!", is_staff=True
    )


# --- Percentile ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "rank", "expected"),
    [
        ([], 50, None),
        ([7.0], 95, 7.0),
        ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50, 5),
        ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95, 10),
        ([10, 1, 5], 50, 5),
        ([1, 2, 3, 4], 0, 1),
    ],
)
def test_percentile(values: list[float], rank: float, expected: float | None) -> None:
    assert metrics.percentile(values, rank) == expected


# --- Métriques ---------------------------------------------------------------------------


def test_dream_metrics(user: Any, make_dream: MakeDream) -> None:
    for seconds in (10, 12, 30):
        dream = make_dream(user, status=Status.TERMINE)
        Dream.objects.filter(pk=dream.pk).update(
            processed_at=dream.created_at + timedelta(seconds=seconds)
        )
    make_dream(user, status=Status.ECHEC)
    make_dream(user, status=Status.TRANSCRIPTION)
    old = make_dream(user, status=Status.ECHEC)
    Dream.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=3))

    result = metrics.dream_metrics(timedelta(hours=24))

    assert (result.created, result.completed, result.failed, result.in_progress) == (5, 3, 1, 1)
    assert result.missing_image == 3
    assert result.success_rate == 75.0
    assert result.processing_p50_s == pytest.approx(12, abs=0.5)
    assert result.processing_p95_s == pytest.approx(30, abs=0.5)


@pytest.mark.django_db
def test_dream_metrics_without_data() -> None:
    result = metrics.dream_metrics(timedelta(days=7))

    assert result.success_rate is None
    assert result.processing_p50_s is None


@pytest.mark.django_db
def test_service_metrics() -> None:
    call(ApiService.TRANSCRIPTION, ms=1000, cost="0.001")
    call(ApiService.TRANSCRIPTION, ms=3000, cost="0.002")
    call(ApiService.TRANSCRIPTION, success=False, ms=60000)
    call(ApiService.EMOTION, ms=800, cost="0.00005")
    call(ApiService.EMOTION, success=False)
    call(ApiService.EMOTION, provider="local", model_name="lexique-fr", ms=1)
    old = call(ApiService.IMAGE, cost="1.0")
    ApiCall.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=2))

    rows = {row.service: row for row in metrics.service_metrics(timedelta(hours=24))}

    transcription = rows["transcription"]
    assert (transcription.calls, transcription.failures) == (3, 1)
    assert transcription.failure_rate == 33.3
    assert transcription.latency_p95_ms == 3000  # les échecs n'entrent pas dans la latence
    assert transcription.cost_usd == Decimal("0.003")
    assert transcription.fallback_rate is None
    emotion = rows["emotion"]
    assert emotion.calls == 2  # le lexique local n'est pas un appel d'API
    assert emotion.fallback_rate == 50.0  # 1 repli sur 2 rêves classés
    assert rows["image"].calls == 0
    assert rows["image"].latency_p50_ms is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("spent", "level", "percent"),
    [("1.00", "success", 10), ("8.50", "warning", 85), ("12.00", "danger", 120)],
)
def test_budget_metrics(settings: Settings, spent: str, level: str, percent: int) -> None:
    settings.AI_MONTHLY_BUDGET_USD = 10.0
    call(ApiService.IMAGE, cost=spent)

    budget = metrics.budget_metrics()

    assert (budget.level, budget.percent) == (level, percent)


@pytest.mark.django_db
def test_recent_errors_newest_first() -> None:
    first = call(ApiService.IMAGE, success=False)
    call(ApiService.IMAGE)
    second = call(ApiService.EMOTION, success=False)

    assert metrics.recent_errors() == [second, first]


# --- Page de supervision ------------------------------------------------------------------


def test_supervision_is_reserved_to_staff(client: Client, user: Any) -> None:
    client.force_login(user)

    response = client.get(reverse("core:supervision"))

    assert response.status_code == 302
    assert "/admin/login/" in response.url


def test_supervision_page_for_staff(
    client: Client, staff: Any, user: Any, make_dream: MakeDream
) -> None:
    make_dream(user, status=Status.TERMINE)
    call(ApiService.TRANSCRIPTION, success=False)
    client.force_login(staff)

    response = client.get(reverse("core:supervision"), {"fenetre": "7j"})
    html = response.content.decode()

    assert response.status_code == 200
    assert response.context["window"] == "7j"
    assert 'data-testid="service-transcription"' in html
    assert "APITimeoutError" in html
    assert 'data-testid="budget"' in html


def test_supervision_unknown_window_falls_back_to_24h(client: Client, staff: Any) -> None:
    client.force_login(staff)

    assert client.get(reverse("core:supervision"), {"fenetre": "1an"}).context["window"] == "24h"


def test_navbar_link_only_for_staff(client: Client, staff: Any, user: Any) -> None:
    client.force_login(user)
    assert reverse("core:supervision") not in client.get("/").content.decode()

    client.force_login(staff)
    assert reverse("core:supervision") in client.get("/").content.decode()


# --- Middlewares ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_health_check_bypasses_allowed_hosts(client: Client) -> None:
    response = client.get("/health/", HTTP_HOST="10.0.0.42:10000")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.django_db
def test_other_pages_still_reject_unknown_hosts(client: Client) -> None:
    assert client.get("/", HTTP_HOST="pirate.example").status_code == 400


@pytest.mark.django_db
def test_server_timing_header(client: Client) -> None:
    assert client.get("/").headers["Server-Timing"].startswith("app;dur=")


def test_slow_requests_are_logged(settings: Settings, caplog: pytest.LogCaptureFixture) -> None:
    settings.SLOW_REQUEST_MS = 0
    middleware = RequestTimingMiddleware(lambda request: HttpResponse())

    with caplog.at_level(logging.WARNING, logger="core.requests"):
        middleware(RequestFactory().get("/reves/"))

    assert "Requête lente : GET /reves/ → 200" in caplog.text


def test_fast_requests_are_not_logged(settings: Settings, caplog: pytest.LogCaptureFixture) -> None:
    settings.SLOW_REQUEST_MS = 60_000
    middleware = RequestTimingMiddleware(lambda request: HttpResponse())

    with caplog.at_level(logging.WARNING, logger="core.requests"):
        middleware(RequestFactory().get("/"))

    assert caplog.text == ""


# --- Logs JSON ----------------------------------------------------------------------------------


def test_json_formatter_outputs_one_json_object() -> None:
    record = logging.makeLogRecord(
        {"name": "dreams.pipeline", "levelname": "INFO", "msg": "Rêve %s traité", "args": (42,)}
    )
    record.duration_ms = 1234

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "Rêve 42 traité"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "dreams.pipeline"
    assert payload["duration_ms"] == 1234
    assert "time" in payload


def test_json_formatter_includes_exception() -> None:
    try:
        raise ValueError("boum")
    except ValueError:
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "échec", None, sys.exc_info())

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boum" in payload["exception"]
