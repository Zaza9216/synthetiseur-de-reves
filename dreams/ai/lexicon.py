"""Classifieur d'émotion de secours, local et sans API, fondé sur un lexique français.

Utilisé uniquement quand le service d'IA est indisponible : il est moins fin
qu'un modèle de langage (pas de prise en compte de la négation ni du contexte),
mais il garantit qu'un rêve reçoit toujours une émotion.
"""

import re
import unicodedata
from collections import Counter

from dreams.models import Emotion

# Débuts de mots (sans accents) caractéristiques de chaque émotion.
LEXICON: dict[str, tuple[str, ...]] = {
    Emotion.HEUREUX: (
        "heureu",
        "joie",
        "joyeu",
        "content",
        "rire",
        "riai",
        "sourire",
        "souri",
        "bonheur",
        "libre",
        "liberte",
        "apais",
        "calme",
        "serein",
        "magnifique",
        "merveill",
        "emerveill",
        "doux",
        "douce",
        "aime",
        "amour",
        "fete",
        "danse",
        "soleil",
        "lumineu",
        "paisible",
    ),
    Emotion.STRESSANT: (
        "peur",
        "angoiss",
        "panique",
        "terrifi",
        "effray",
        "poursui",
        "fuir",
        "fuyai",
        "tomb",
        "chute",
        "cauchemar",
        "monstre",
        "crier",
        "criai",
        "hurl",
        "piege",
        "enferm",
        "noyai",
        "noyer",
        "noyade",
        "etouff",
        "stress",
        "danger",
        "menac",
        "sang",
        "mort",
        "perdu",
        "retard",
        "examen",
        "noir",
    ),
    Emotion.TRISTE: (
        "triste",
        "pleur",
        "larme",
        "chagrin",
        "seul",
        "solitude",
        "manque",
        "nostalg",
        "regret",
        "deuil",
        "absent",
        "abandonn",
        "vide",
        "melancol",
        "quitt",
        "adieu",
    ),
    Emotion.COLERE: (
        "colere",
        "furieu",
        "enerv",
        "rageu",
        "enrag",
        "disput",
        "frapp",
        "injust",
        "agace",
        "frustr",
        "haine",
        "haissai",
        "deteste",
        "battu",
        "bagarre",
        "insult",
        "revolt",
    ),
    Emotion.SURPRENANT: (
        "etrange",
        "bizarre",
        "surpr",
        "soudain",
        "inattendu",
        "absurde",
        "incroyable",
        "transform",
        "magique",
        "flott",
        "volai",
        "voler",
        "volant",
        "geant",
        "mysteri",
        "irreel",
    ),
}

# Score attribué quand aucun mot du lexique n'est trouvé.
NEUTRAL_SCORE = 0.5
# Plafond de confiance : un lexique ne justifie jamais une certitude élevée.
MAX_LEXICON_SCORE = 0.8


def _normalize(text: str) -> list[str]:
    """Met le texte en minuscules, retire les accents et le découpe en mots."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.findall(r"[a-z]+", ascii_text)


def classify_with_lexicon(text: str) -> tuple[str, float]:
    """Détermine l'émotion dominante d'un texte en comptant les mots du lexique.

    Args:
        text: La transcription du rêve.

    Returns:
        Un couple ``(émotion, score)``. Le score est la part des mots
        émotionnels qui relèvent de l'émotion retenue, plafonnée à
        ``MAX_LEXICON_SCORE``. Sans mot émotionnel, le rêve est neutre.
    """
    counts: Counter[str] = Counter()
    for word in _normalize(text):
        for emotion, stems in LEXICON.items():
            if any(word.startswith(stem) for stem in stems):
                counts[emotion] += 1

    if not counts:
        return Emotion.NEUTRE, NEUTRAL_SCORE

    # À égalité, l'ordre du lexique départage (heureux, stressant, triste…).
    order = list(LEXICON)
    emotion, hits = max(counts.items(), key=lambda item: (item[1], -order.index(item[0])))
    score = min(hits / sum(counts.values()), MAX_LEXICON_SCORE)
    return emotion, round(score, 2)
