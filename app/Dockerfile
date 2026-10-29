# Hiss — Flask issue tracker (teaching image)
# Textbook-readable single-stage build: base, deps, source, non-root, migration+ gunicorn.
# Update with: docker buildx imagetools inspect python:3.13-slim-trixie
# Review the new multi-platform digest and rebuild/test before replacing it.
FROM python:3.13-slim-trixie@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb

ARG VCS_REF=unknown
ARG SOURCE_URL=unknown
ARG IMAGE_VERSION=unknown
LABEL org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.source=$SOURCE_URL \
      org.opencontainers.image.version=$IMAGE_VERSION

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first for layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source (respects .dockerignore)
COPY . .

# Create non-root user and prepare entrypoint
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app \
    && chmod +x ./docker-entrypoint.sh

# hadolint ignore=DL3066
USER appuser

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
