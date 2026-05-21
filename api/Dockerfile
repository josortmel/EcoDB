# EcoDB API — Dockerfile (Tarea 1.4 plan maestro v3, hardening adv-seg Loop 1)
# Esqueleto minimalista. Crece con cada tarea de Fase 1: auth, CRUD, search, etc.

FROM python:3.12-slim

# El repo apt.debian.org rechaza HTTP plano (Fastly 451) — pasar a HTTPS antes
# de cualquier apt-get update. python:3.12-slim YA trae ca-certificates.
RUN sed -i 's|http://deb\.debian\.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# VS2 (adv-seg): no correr como root. Crear usuario apiuser UID 1000.
RUN groupadd --system --gid 1000 apiuser \
    && useradd --system --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin apiuser

WORKDIR /app

# Tarea 3.0 — HF cache para GLiNER. apiuser no tiene home (--no-create-home),
# asi que ponemos el cache en /app/.cache/huggingface, owned por apiuser.
# docker-compose.yml monta named volume aqui para sobrevivir force-recreate.
ENV HF_HOME=/app/.cache/huggingface
RUN mkdir -p /app/.cache/huggingface && chown -R apiuser:apiuser /app/.cache

# Layer separado para deps — cache friendly: requirements.txt cambia menos que el codigo.
COPY --chown=apiuser:apiuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia explicita de modulos del API. bootstrap_first_apikey.py se incluye para
# poder ejecutarlo con `docker exec` contra el postgres en el primer arranque.
COPY --chown=apiuser:apiuser admin.py agents.py auth.py background.py bootstrap_first_apikey.py chunker.py classifier.py db.py documents.py embeddings_client.py entity_normalization.py events.py gliner_service.py graph.py llm_provider.py main.py memories.py onboarding.py parsers.py permissions.py projects.py rate_limit.py reranker.py search.py settings.py stats.py teams.py telemetry.py telemetry_api.py users.py worker.py workspaces.py ./

# Pre-cache reranker model so first request isn't slow (runs as root, writes to HF_HOME).
# NB1: revision must match RERANKER_REVISION at runtime — same SHA = same HF cache key.
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', revision='c5ee24cb16019beea0893ab7796b1df96625c6b8')"
# NB3: pre-cache ran as root — fix ownership so apiuser can read the cached files.
RUN chown -R apiuser:apiuser /app/.cache

# Cambiar a usuario no-root antes de ejecutar la app.
USER apiuser

EXPOSE 8080

# Healthcheck integrado: docker compose y k8s pueden ver liveness sin codigo extra.
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail --silent http://localhost:8080/health || exit 1

# VS1 (adv-seg): logging HTTP activo desde el primer arranque para forensics.
# VS5 (adv-seg): --no-server-header suprime el `Server: uvicorn` que de otra forma
# se añade DESPUES del middleware del app. La supresion debe ser a nivel uvicorn,
# no de middleware — el orden es app middleware -> uvicorn server response.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
