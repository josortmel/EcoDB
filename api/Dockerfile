# EcoDB API — Dockerfile (Tarea 1.4 plan maestro v3, hardening adv-seg Loop 1)
# Esqueleto minimalista. Crece con cada tarea de Fase 1: auth, CRUD, search, etc.

FROM python:3.12-slim

# El repo apt.debian.org rechaza HTTP plano (Fastly 451) — pasar a HTTPS antes
# de cualquier apt-get update. python:3.12-slim YA trae ca-certificates.
RUN sed -i 's|http://deb\.debian\.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg gosu \
    && rm -rf /var/lib/apt/lists/*

# VS2 (adv-seg): no correr como root. Crear usuario apiuser UID 1000.
RUN groupadd --system --gid 1000 apiuser \
    && useradd --system --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin apiuser

WORKDIR /app

# Tarea 3.0 — HF cache para GLiNER. apiuser no tiene home (--no-create-home),
# asi que ponemos el cache en /app/.cache/huggingface, owned por apiuser.
# docker-compose.yml monta named volume aqui para sobrevivir force-recreate.
ENV HF_HOME=/app/.cache/huggingface
RUN mkdir -p /app/.cache/huggingface /app/media && chown -R apiuser:apiuser /app/.cache /app/media

# Layer separado para deps — cache friendly: requirements.txt cambia menos que el codigo.
COPY --chown=apiuser:apiuser api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ecodb-langchain SDK (used by cell_worker via LangChain)
COPY --chown=apiuser:apiuser ecodb-langchain /tmp/ecodb-langchain
RUN pip install --no-cache-dir "/tmp/ecodb-langchain[openai]" && rm -rf /tmp/ecodb-langchain

# Copia explicita de modulos del API.
COPY --chown=apiuser:apiuser api/admin.py api/agents.py api/auth.py api/background.py api/bootstrap_first_apikey.py api/briefing.py api/cases.py api/cell_configs.py api/cell_templates.py api/cell_worker.py api/cells.py api/chunker.py api/classifier.py api/clusters.py api/crypto.py api/db.py api/documents.py api/embeddings_client.py api/entity_normalization.py api/events.py api/foresights.py api/gliner_service.py api/graph.py api/llm_provider.py api/main.py api/migrations.py api/memories.py api/onboarding.py api/pagination.py api/parsers.py api/permissions.py api/projects.py api/providers.py api/rate_limit.py api/reranker.py api/search.py api/settings.py api/shared_models.py api/skills.py api/stats.py api/teams.py api/telemetry.py api/telemetry_api.py api/users.py api/worker.py api/workspaces.py ./

COPY --chown=root:root api/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Pre-cache reranker model so first request isn't slow (runs as root, writes to HF_HOME).
# NB1: revision must match RERANKER_REVISION at runtime — same SHA = same HF cache key.
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', revision='c5ee24cb16019beea0893ab7796b1df96625c6b8')"
# NB3: pre-cache ran as root — fix ownership so apiuser can read the cached files.
RUN chown -R apiuser:apiuser /app/.cache

EXPOSE 8080

# Healthcheck integrado: docker compose y k8s pueden ver liveness sin codigo extra.
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail --silent http://localhost:8080/health || exit 1

# VS1 (adv-seg): logging HTTP activo desde el primer arranque para forensics.
# VS5 (adv-seg): --no-server-header suprime el `Server: uvicorn` que de otra forma
# se añade DESPUES del middleware del app. La supresion debe ser a nivel uvicorn,
# no de middleware — el orden es app middleware -> uvicorn server response.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
