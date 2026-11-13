"""Commande ``seed_demo_dreams`` : crée des rêves de démonstration, sans appel d'API.

Usage :
    uv run python manage.py seed_demo_dreams --username demo --count 40 --weeks 12
"""

import random
from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from django.utils import timezone

from dreams.models import Dream, Emotion, EmotionMethod, Status

DEMO_PASSWORD = "Demo-Reves-2026!"

# Récits d'exemple par émotion.
SAMPLES: dict[str, list[str]] = {
    Emotion.HEUREUX: [
        "Je marchais sur une plage au coucher du soleil avec ma grand-mère, on riait aux éclats.",
        "Je volais au-dessus d'une ville de verre sous un ciel violet, je me sentais libre.",
        "On fêtait mon anniversaire dans un jardin rempli de lanternes, tout le monde dansait.",
    ],
    Emotion.STRESSANT: [
        "Quelqu'un me poursuivait dans un parking souterrain et mes jambes refusaient d'avancer.",
        "J'arrivais en retard à un examen dont je n'avais jamais vu le sujet.",
        "Je tombais sans fin dans un puits noir, sans réussir à crier.",
    ],
    Emotion.TRISTE: [
        "Je revenais dans la maison de mon enfance, elle était vide et silencieuse.",
        "Mon vieux chien m'attendait sur le quai d'une gare, puis le train l'emportait.",
    ],
    Emotion.COLERE: [
        "Un collègue s'attribuait mon travail devant tout le monde et personne ne m'écoutait.",
        "Je me disputais avec un guichetier qui refusait obstinément de m'ouvrir la porte.",
    ],
    Emotion.SURPRENANT: [
        "Mon chat parlait couramment japonais et la cuisine se transformait en aquarium géant.",
        "Les escaliers de l'immeuble montaient vers la mer, et ça semblait normal.",
    ],
    Emotion.NEUTRE: [
        "Je faisais mes courses au supermarché, puis je rentrais tranquillement chez moi.",
        "J'attendais le bus en lisant un journal dont je ne me souviens plus.",
    ],
}
# Poids réalistes : plus de rêves heureux et stressants que de rêves en colère.
WEIGHTS: dict[str, int] = {
    Emotion.HEUREUX: 30,
    Emotion.STRESSANT: 28,
    Emotion.TRISTE: 12,
    Emotion.COLERE: 8,
    Emotion.SURPRENANT: 14,
    Emotion.NEUTRE: 8,
}


class Command(BaseCommand):
    """Crée un utilisateur de démonstration et des rêves répartis dans le temps."""

    help = "Crée des rêves de démonstration (sans appel aux API d'IA)."

    def add_arguments(self, parser: CommandParser) -> None:
        """Déclare les options de la commande."""
        parser.add_argument("--username", default="demo")
        parser.add_argument("--count", type=int, default=40)
        parser.add_argument("--weeks", type=int, default=12)
        parser.add_argument(
            "--seed", type=int, default=None, help="Graine pour un résultat reproductible."
        )
        parser.add_argument(
            "--clear", action="store_true", help="Supprime d'abord les rêves de l'utilisateur."
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Crée l'utilisateur si besoin, puis les rêves."""
        rng = random.Random(options["seed"])
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=options["username"],
            defaults={"email": f"{options['username']}@example.com"},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
            self.stdout.write(
                f"Utilisateur « {user.username} » créé (mot de passe : {DEMO_PASSWORD})."
            )
        if options["clear"]:
            user.dreams.all().delete()

        emotions = list(WEIGHTS)
        now = timezone.now()
        span_minutes = options["weeks"] * 7 * 24 * 60
        for _ in range(options["count"]):
            emotion = rng.choices(emotions, weights=[WEIGHTS[e] for e in emotions])[0]
            dream = Dream.objects.create(
                user=user,
                transcription=rng.choice(SAMPLES[emotion]),
                emotion=emotion,
                emotion_score=round(rng.uniform(0.6, 0.97), 2),
                emotion_method=EmotionMethod.IA,
                status=Status.TERMINE,
                audio_duration=round(rng.uniform(20, 150), 1),
            )
            created_at = now - timedelta(minutes=rng.randint(0, span_minutes))
            Dream.objects.filter(pk=dream.pk).update(
                created_at=created_at, processed_at=created_at + timedelta(seconds=14)
            )
        self.stdout.write(self.style.SUCCESS(f"{options['count']} rêves de démonstration créés."))
