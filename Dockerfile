FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*
# venv lives outside /app so the bind mount in compose.yaml doesn't hide it
# HOME=/tmp: compose runs this as a non-root UID with no home dir of its own
# (needed so gunicorn, in prod mode, can write its control socket)
ENV UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY . .
# Without the bind mount (prod stack), /app is root-owned: let the non-root
# runtime UID write collectstatic output and player uploads.
RUN mkdir -p staticfiles images && chown 1000:1000 staticfiles images
EXPOSE 8000
# Dev (DEBUG=True in .env): Django's dev server, autoreload, static files served
# straight from game/static/ by django.contrib.staticfiles.
# Prod (DEBUG=False): collectstatic + gunicorn, static files served by WhiteNoise.
CMD ["sh", "-c", "python manage.py migrate --noinput && if [ \"$DEBUG\" = \"True\" ]; then python manage.py runserver 0.0.0.0:8000; else python manage.py collectstatic --noinput && gunicorn tcg.wsgi:application --bind 0.0.0.0:8000; fi"]
