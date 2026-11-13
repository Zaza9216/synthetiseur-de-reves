#!/usr/bin/env sh
# Démarrage du conteneur en production : base à jour, administrateur, serveur web.
set -e

python manage.py migrate --noinput
python manage.py ensure_admin

# gthread : chaque processus traite plusieurs requêtes en parallèle (fils d'exécution),
# utile pendant que la page de suivi interroge le serveur toutes les 2 secondes.
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --worker-class gthread \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout 120 \
  --access-logfile -
