"""Test de charge du Synthétiseur de rêves (Locust).

Chaque utilisateur virtuel crée son compte, consulte son tableau de bord et
ses rêves, et envoie de temps en temps un nouveau rêve dont il suit le
traitement comme le ferait la page (interrogation toutes les 2 secondes).

Le serveur doit tourner avec ``AI_BACKEND=fake`` : les services d'IA sont
simulés avec leurs durées réelles, sans appel ni coût. Mode d'emploi :
voir ``loadtests/README.md``.
"""

import time
import uuid

from locust import HttpUser, between, events, task

# Faux fichier audio WebM (signature valide + données), environ 40 Ko.
AUDIO_WEBM = b"\x1a\x45\xdf\xa3" + bytes(40_000)
PASSWORD = "Charge-Test-2026!"
POLL_INTERVAL_S = 2
MAX_WAIT_S = 180


class Dreamer(HttpUser):
    """Utilisateur qui raconte et consulte ses rêves."""

    wait_time = between(2, 6)  # temps de lecture entre deux actions

    def on_start(self) -> None:
        """Crée un compte (l'inscription connecte automatiquement)."""
        self.dream_ids: list[int] = []
        username = f"charge_{uuid.uuid4().hex[:10]}"
        self.client.get("/comptes/inscription/", name="Inscription (page)")
        self.client.post(
            "/comptes/inscription/",
            data={
                "username": username,
                "email": f"{username}@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "csrfmiddlewaretoken": self.client.cookies.get("csrftoken", ""),
            },
            name="Inscription (envoi)",
        )

    @task(5)
    def dashboard(self) -> None:
        """Tableau de bord par défaut (statistiques, graphique, rêves)."""
        self.client.get("/reves/", name="Tableau de bord")

    @task(2)
    def dashboard_filtered(self) -> None:
        """Tableau de bord filtré sur une période et une émotion."""
        self.client.get(
            "/reves/?start=2026-01-01&end=2026-12-31&emotion=heureux",
            name="Tableau de bord (filtré)",
        )

    @task(3)
    def dream_detail(self) -> None:
        """Page d'un rêve déjà créé."""
        if self.dream_ids:
            dream_id = self.dream_ids[-1]
            self.client.get(f"/reves/{dream_id}/", name="Détail d'un rêve")

    @task(1)
    def tell_a_dream(self) -> None:
        """Envoie un rêve et suit son traitement jusqu'au résultat."""
        start = time.perf_counter()
        with self.client.post(
            "/reves/nouveau/",
            files={"audio": ("reve.webm", AUDIO_WEBM, "audio/webm")},
            data={"audio_duration": "45"},
            headers={
                "Accept": "application/json",
                "X-CSRFToken": self.client.cookies.get("csrftoken", ""),
            },
            name="Envoi d'un rêve",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"HTTP {response.status_code}")
                return
            dream_id = response.json()["id"]
            self.dream_ids.append(dream_id)

        status = "en_attente"
        while time.perf_counter() - start < MAX_WAIT_S:
            time.sleep(POLL_INTERVAL_S)
            poll = self.client.get(f"/reves/{dream_id}/statut/", name="Suivi du traitement")
            if poll.ok:
                payload = poll.json()
                status = payload["status"]
                if not payload["is_processing"]:
                    break

        elapsed_ms = (time.perf_counter() - start) * 1000
        events.request.fire(
            request_type="PIPELINE",
            name="Rêve complet (envoi → résultat)",
            response_time=elapsed_ms,
            response_length=0,
            exception=None if status == "termine" else RuntimeError(f"statut final : {status}"),
            context={},
        )
