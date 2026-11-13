#!/usr/bin/env bash
# Installation locale du Synthétiseur de rêves (sans Docker).
# Usage : ./scripts/install.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "→ Installation de uv (gestionnaire Python)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "→ Installation de Python 3.12 et des dépendances…"
uv sync

if [ ! -f .env ]; then
  echo "→ Création du fichier .env à partir de .env.example…"
  secret=$(uv run python -c "import secrets; print(secrets.token_urlsafe(50))")
  sed "s|^SECRET_KEY=.*|SECRET_KEY=${secret}|" .env.example > .env
  echo "  Pensez à renseigner vos clés API dans .env"
fi

echo "→ Création de la base de données…"
uv run python manage.py migrate

echo
echo "✔ Installation terminée. Lancer le serveur avec :"
echo "  uv run python manage.py runserver"
