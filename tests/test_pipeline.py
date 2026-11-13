"""Tests du pipeline de traitement des rêves et des pages de suivi."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from pytest_django.fixtures import Settings

from dreams import pipeline
from dreams.ai.errors import AIServiceError
from dreams.models import Dream, Status
from dreams.pipeline import enqueue_dream, process_dream, retry_dream
from tests.conftest import fake_audio

MakeDream = Callable[..., Dream]


@pytest.fixture
def pending_dream(user: Any, make_dream: MakeDream) -> Dream:
    """Rêve qui vient d'être envoyé : audio présent, rien d'autre."""
    return make_dream(
        user,
        audio=fake_audio(),
        transcription="",
        emotion="",
        emotion_score=None,
        status=Status.EN_ATTENTE,
    )


@pytest.fixture
def fake_transcribe() -> Any:
    """Remplace la transcription par un double qui renvoie un texte."""
    with patch(
        "dreams.pipeline.transcribe_dream", return_value="Je nageais avec des baleines."
    ) as mock:
        yield mock


def make_stalled(dream: Dream, status: Status = Status.TRANSCRIPTION) -> None:
    """Simule un traitement interrompu il y a longtemps."""
    Dream.objects.filter(pk=dream.pk).update(
        status=status, updated_at=timezone.now() - timedelta(hours=1)
    )
    dream.refresh_from_db()


# --- Pipeline ------------------------------------------------------------------------


def test_process_dream_runs_steps_and_completes(pending_dream: Dream, fake_transcribe: Any) -> None:
    process_dream(pending_dream.pk)

    pending_dream.refresh_from_db()
    assert pending_dream.status == Status.TERMINE
    assert pending_dream.transcription == "Je nageais avec des baleines."
    assert pending_dream.processed_at is not None
    assert pending_dream.error_message == ""
    fake_transcribe.assert_called_once()


def test_process_dream_skips_steps_already_done(pending_dream: Dream, fake_transcribe: Any) -> None:
    Dream.objects.filter(pk=pending_dream.pk).update(transcription="Déjà transcrit")

    process_dream(pending_dream.pk)

    pending_dream.refresh_from_db()
    assert pending_dream.status == Status.TERMINE
    assert pending_dream.transcription == "Déjà transcrit"
    fake_transcribe.assert_not_called()


def test_ai_error_marks_dream_as_failed_with_user_message(pending_dream: Dream) -> None:
    error = AIServiceError("Le service d'IA est injoignable pour le moment. Réessayez.")
    with patch("dreams.pipeline.transcribe_dream", side_effect=error):
        process_dream(pending_dream.pk)

    pending_dream.refresh_from_db()
    assert pending_dream.status == Status.ECHEC
    assert pending_dream.error_message == error.user_message
    assert pending_dream.can_retry


def test_unexpected_error_marks_dream_as_failed_with_generic_message(
    pending_dream: Dream,
) -> None:
    with patch("dreams.pipeline.transcribe_dream", side_effect=KeyError("bug")):
        process_dream(pending_dream.pk)

    pending_dream.refresh_from_db()
    assert pending_dream.status == Status.ECHEC
    assert pending_dream.error_message == pipeline.GENERIC_ERROR_MESSAGE


def test_dream_already_being_processed_is_not_processed_twice(
    pending_dream: Dream, fake_transcribe: Any
) -> None:
    Dream.objects.filter(pk=pending_dream.pk).update(status=Status.TRANSCRIPTION)

    process_dream(pending_dream.pk)

    fake_transcribe.assert_not_called()


@pytest.mark.django_db
def test_unknown_dream_is_ignored(fake_transcribe: Any) -> None:
    process_dream(999_999)

    fake_transcribe.assert_not_called()


def test_dream_deleted_during_processing_is_not_recreated(pending_dream: Dream) -> None:
    def delete_then_return_text(dream: Dream) -> str:
        Dream.objects.filter(pk=dream.pk).delete()
        return "texte"

    with patch("dreams.pipeline.transcribe_dream", side_effect=delete_then_return_text):
        process_dream(pending_dream.pk)

    assert not Dream.objects.filter(pk=pending_dream.pk).exists()


def test_dream_deleted_just_before_completion_is_not_recreated(
    pending_dream: Dream, fake_transcribe: Any
) -> None:
    Dream.objects.filter(pk=pending_dream.pk).update(transcription="Déjà transcrit")
    real_save = pipeline._save

    def delete_on_final_save(dream: Dream, *fields: str) -> None:
        if "processed_at" in fields:
            Dream.objects.filter(pk=dream.pk).delete()
        real_save(dream, *fields)

    with patch("dreams.pipeline._save", side_effect=delete_on_final_save):
        process_dream(pending_dream.pk)

    assert not Dream.objects.filter(pk=pending_dream.pk).exists()


def test_save_never_recreates_a_deleted_dream(pending_dream: Dream) -> None:
    Dream.objects.filter(pk=pending_dream.pk).delete()
    pending_dream.transcription = "texte"

    with pytest.raises(pipeline.DreamDeletedError):
        pipeline._save(pending_dream, "transcription")

    assert not Dream.objects.exists()


# --- Mise en file -----------------------------------------------------------------------


def test_enqueue_off_does_nothing(pending_dream: Dream, fake_transcribe: Any) -> None:
    enqueue_dream(pending_dream.pk)

    fake_transcribe.assert_not_called()


def test_enqueue_sync_processes_immediately(
    pending_dream: Dream, fake_transcribe: Any, settings: Settings
) -> None:
    settings.DREAM_PROCESSING_MODE = "sync"

    enqueue_dream(pending_dream.pk)

    pending_dream.refresh_from_db()
    assert pending_dream.status == Status.TERMINE


def test_enqueue_thread_submits_after_commit(
    pending_dream: Dream,
    settings: Settings,
    django_capture_on_commit_callbacks: Callable[..., Any],
) -> None:
    settings.DREAM_PROCESSING_MODE = "thread"
    executor = MagicMock()

    with (
        patch("dreams.pipeline._executor", return_value=executor),
        django_capture_on_commit_callbacks(execute=True),
    ):
        enqueue_dream(pending_dream.pk)

    executor.submit.assert_called_once_with(pipeline._process_in_thread, pending_dream.pk)


def test_thread_worker_processes_and_releases_connection(pending_dream: Dream) -> None:
    with (
        patch("dreams.pipeline.process_dream") as process,
        patch("dreams.pipeline.close_old_connections") as close,
    ):
        pipeline._process_in_thread(pending_dream.pk)

    process.assert_called_once_with(pending_dream.pk)
    close.assert_called_once()


def test_executor_is_shared(settings: Settings) -> None:
    pipeline._executor.cache_clear()
    settings.DREAM_PROCESSING_WORKERS = 3

    executor = pipeline._executor()

    assert executor is pipeline._executor()
    assert executor._max_workers == 3
    executor.shutdown(wait=False)
    pipeline._executor.cache_clear()


# --- Blocage et relance -----------------------------------------------------------------


def test_recent_processing_is_not_stalled(pending_dream: Dream) -> None:
    Dream.objects.filter(pk=pending_dream.pk).update(status=Status.TRANSCRIPTION)
    pending_dream.refresh_from_db()

    assert not pending_dream.is_stalled
    assert not pending_dream.can_retry


def test_old_processing_is_stalled(pending_dream: Dream) -> None:
    make_stalled(pending_dream)

    assert pending_dream.is_stalled
    assert pending_dream.can_retry


def test_finished_dream_is_never_stalled(user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user, status=Status.TERMINE)
    Dream.objects.filter(pk=dream.pk).update(updated_at=timezone.now() - timedelta(days=3))
    dream.refresh_from_db()

    assert not dream.is_stalled


def test_retry_failed_dream_requeues_it(pending_dream: Dream) -> None:
    Dream.objects.filter(pk=pending_dream.pk).update(status=Status.ECHEC, error_message="x")
    pending_dream.refresh_from_db()

    with patch("dreams.pipeline.enqueue_dream") as enqueue:
        assert retry_dream(pending_dream) is True

    pending_dream.refresh_from_db()
    assert pending_dream.status == Status.EN_ATTENTE
    assert pending_dream.error_message == ""
    enqueue.assert_called_once_with(pending_dream.pk)


def test_retry_stalled_dream_requeues_it(pending_dream: Dream) -> None:
    make_stalled(pending_dream)

    with patch("dreams.pipeline.enqueue_dream"):
        assert retry_dream(pending_dream) is True


def test_retry_finished_dream_is_refused(user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user, status=Status.TERMINE)

    with patch("dreams.pipeline.enqueue_dream") as enqueue:
        assert retry_dream(dream) is False

    enqueue.assert_not_called()


def test_retry_race_condition_requeues_only_once(pending_dream: Dream) -> None:
    Dream.objects.filter(pk=pending_dream.pk).update(status=Status.ECHEC)
    pending_dream.refresh_from_db()
    stale_copy = Dream.objects.get(pk=pending_dream.pk)

    with patch("dreams.pipeline.enqueue_dream") as enqueue:
        first = retry_dream(pending_dream)
        second = retry_dream(stale_copy)  # double clic : copie obsolète du même rêve

    assert (first, second) == (True, False)
    enqueue.assert_called_once()


# --- Pages ----------------------------------------------------------------------------


def test_creating_a_dream_enqueues_its_processing(client: Client, user: Any) -> None:
    from tests.test_dreams_create import audio

    client.force_login(user)
    with patch("dreams.views.enqueue_dream") as enqueue:
        client.post(reverse("dreams:create"), {"audio": audio()})

    enqueue.assert_called_once_with(Dream.objects.get().pk)


def test_status_endpoint_returns_processing_state(
    client: Client, user: Any, pending_dream: Dream
) -> None:
    client.force_login(user)

    response = client.get(reverse("dreams:status", args=[pending_dream.pk]))

    assert response.status_code == 200
    assert response.json() == {
        "status": "en_attente",
        "status_label": "En attente",
        "is_processing": True,
        "can_retry": False,
        "error_message": "",
    }


def test_status_endpoint_of_someone_elses_dream_returns_404(
    client: Client, other_user: Any, pending_dream: Dream
) -> None:
    client.force_login(other_user)

    response = client.get(reverse("dreams:status", args=[pending_dream.pk]))

    assert response.status_code == 404


def test_status_endpoint_requires_login(client: Client, pending_dream: Dream) -> None:
    response = client.get(reverse("dreams:status", args=[pending_dream.pk]))

    assert response.status_code == 401


def test_retry_view_relaunches_failed_dream(
    client: Client, user: Any, pending_dream: Dream
) -> None:
    Dream.objects.filter(pk=pending_dream.pk).update(status=Status.ECHEC)
    client.force_login(user)

    with patch("dreams.pipeline.enqueue_dream"):
        response = client.post(reverse("dreams:retry", args=[pending_dream.pk]), follow=True)

    pending_dream.refresh_from_db()
    assert pending_dream.status == Status.EN_ATTENTE
    assert "a été relancé" in response.content.decode()


def test_retry_view_refuses_dream_in_progress(
    client: Client, user: Any, pending_dream: Dream
) -> None:
    client.force_login(user)

    response = client.post(reverse("dreams:retry", args=[pending_dream.pk]), follow=True)

    assert "ne peut pas être relancé" in response.content.decode()


def test_retry_view_rejects_get_and_other_users(
    client: Client, other_user: Any, pending_dream: Dream
) -> None:
    client.force_login(other_user)

    assert client.get(reverse("dreams:retry", args=[pending_dream.pk])).status_code == 405
    assert client.post(reverse("dreams:retry", args=[pending_dream.pk])).status_code == 404


def test_detail_shows_live_progress_while_processing(
    client: Client, user: Any, pending_dream: Dream
) -> None:
    Dream.objects.filter(pk=pending_dream.pk).update(status=Status.TRANSCRIPTION)
    client.force_login(user)

    response = client.get(reverse("dreams:detail", args=[pending_dream.pk]))
    html = response.content.decode()

    assert 'id="processing-panel"' in html
    assert "js/dream-status.js" in html
    states = [step["state"] for step in response.context["progress_steps"]]
    assert states == ["active", "todo", "todo"]


def test_detail_shows_retry_button_on_failure(
    client: Client, user: Any, pending_dream: Dream
) -> None:
    Dream.objects.filter(pk=pending_dream.pk).update(
        status=Status.ECHEC, error_message="Le service d'IA est injoignable."
    )
    client.force_login(user)

    html = client.get(reverse("dreams:detail", args=[pending_dream.pk])).content.decode()

    assert escape("Le service d'IA est injoignable.") in html
    assert reverse("dreams:retry", args=[pending_dream.pk]) in html
    assert "js/dream-status.js" not in html


def test_detail_shows_retry_button_when_stalled(
    client: Client, user: Any, pending_dream: Dream
) -> None:
    make_stalled(pending_dream)
    client.force_login(user)

    html = client.get(reverse("dreams:detail", args=[pending_dream.pk])).content.decode()

    assert "Le traitement semble bloqué." in html
    assert "js/dream-status.js" not in html
