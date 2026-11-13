# Image de production du Synthétiseur de rêves.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dépendances d'abord (mises en cache tant que le lockfile ne change pas)
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput

# Ne pas exécuter l'application en root
RUN useradd --create-home appuser && mkdir -p /app/media && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120 --access-logfile -"]
