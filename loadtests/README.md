# Test de charge (Locust)

Mesure la capacité de l'application avec N utilisateurs simultanés, **sans appel ni coût d'IA** :
le serveur tourne avec `AI_BACKEND=fake`, qui simule les durées réelles des API
(transcription ≈ 1,2 s, émotion ≈ 0,9 s, image ≈ 10,2 s).

## Scénario (`locustfile.py`)
Chaque utilisateur virtuel crée son compte, puis enchaîne (pause de 2 à 6 s entre deux actions) :

| Action | Poids |
|---|---|
| Tableau de bord | 5 |
| Tableau de bord filtré | 2 |
| Page d'un de ses rêves | 3 |
| **Envoi d'un rêve**, puis suivi toutes les 2 s jusqu'au résultat | 1 |

La durée « Rêve complet (envoi → résultat) » est remontée comme une mesure à part.

## Lancer le test
```bash
# 1. Serveur dans des conditions proches de la production (PostgreSQL, Gunicorn, DEBUG=False)
export DATABASE_URL=postgres://…  DEBUG=False SECURE_SSL_REDIRECT=False SECURE_COOKIES=False \
       AI_BACKEND=fake MEDIA_STORAGE=database DREAM_DAILY_LIMIT=1000 PORT=8800 SECRET_KEY=…
uv run python manage.py migrate && uv run python manage.py collectstatic --noinput
sh scripts/start.sh

# 2. Charge : 50 utilisateurs, arrivée de 5 par seconde, pendant 150 s
uv run locust -f loadtests/locustfile.py --headless -u 50 -r 5 -t 150s \
  --host http://localhost:8800 --csv resultats --html resultats.html
```
`AI_BACKEND=fake` est **refusé au démarrage** si l'application tourne sur Render (sécurité).

Résultats et analyse : [`docs/test-de-charge.md`](../docs/test-de-charge.md).
