# Cómo está fabricada la imagen de producción (28-oct-2026, #712)

Producción NO sale de un `docker build` del repo: sale de capas pequeñas (`deploy/overlays/`) puestas una encima de
otra sobre la imagen viva. Este fichero dice el orden, para poder rehacerla si se pierde. El inventario exacto de lo
que lleva hoy la imagen viva está en `deploy/inventario/` (apt con `dpkg-query`, Python con `pip list --format=json`,
nunca `pip freeze`: no lista pip/setuptools ni versiona los `@ file://`).

Las capas se construyen desde la RAÍZ del repo (`docker build -f deploy/overlays/Dockerfile.overlayNNN -t <etiqueta> .`)
porque copian `api/...` y `sql/...`. Cada `FROM` apunta a una etiqueta LOCAL: antes de construir una capa se retaguea
la imagen viva con esa etiqueta (`docker tag ecodb-api:0.25.0 ecodb-api:0.25.0-preNNN`), que es también la vuelta atrás.

## ecodb-api:0.25.0 (api, worker y ecodb-cell usan la misma imagen)

| Paso | Capa | Encima de | Resultado | Qué cambia |
|---|---|---|---|---|
| 0 | — | — | `0.25.0-prevo` = f87a9d9d | base (copia en `F:\docker_respaldo\`) |
| … | `overlay`, `overlay513`, `overlay393`, `overlay500` | `pre494` / `pre393` | `0.25.0-pre393` = c725e774 → `pre386` = 9ba0bad2 | módulos de #494, #513, #393 y #500 (15-oct; detalle en CLAUDE.md, secciones del 13 y 15-oct) |
| 1 | `overlay386-api` | `pre386` (9ba0bad2) | 0e10528f | pip: fastapi 0.141.0, starlette 1.7.0, PyJWT 2.15.1, python-multipart 0.0.32 |
| 2 | `overlay443` | `pre443` (0e10528f) | dc59dd20 | `graph.py` de f01cdac |
| 3 | `overlay561-api` + `overlay561-apt-api` | `pre561` (dc59dd20) | e1b51888 | pip (urllib3 2.8.0, langgraph-sdk 0.4.4, pip 26.2) + `apt upgrade` |
| 4 | `overlay605` | `pre605` (e1b51888) | 65fbe310 | `classifier.py` de 5bc08fa |
| 5 | `overlay569` | `pre569` (65fbe310) | **b32663fb = viva el 28-oct** | `graph.py`, `migrations.py` de 7ebe953 + `sql/migrate_5.4.1_…` |
| 6 | `overlay701` | `pre701` (b32663fb) | pendiente (#784) | `cell_worker.py`, `cell_configs.py`, `settings.py` de 6b08a5c (#701/#716/#717) |

## ecodb-mcp:1.8.0

| Paso | Capa | Encima de | Resultado | Qué cambia |
|---|---|---|---|---|
| 0 | — | — | `1.8.0-prevo` | base |
| 1 | `overlay386-mcp`, `overlay386-mcp2` | `pre386` / `386` | 1a22c1a9 | mcp 1.29.1, PyJWT 2.15.1 |
| 2 | `overlay561-mcp` + `overlay561-apt-mcp` | `pre561` / `561` | 1d436f8c | mcp 1.30.0 (GHSA-84m7-p3x7-pcfv) + `apt upgrade` |
| 3 | `overlay569-mcp` | `1.8.0` (1d436f8c) | **46fb40ea = viva el 28-oct** | `mcp/server.py` de 7ebe953 |

Las de embeddings, ner y postgres (`overlay561-emb*`, `-ner`, `-apt-*`) son del 16-oct (#561) y siguen el mismo patrón.

## Por qué un build en frío del repo NO da esta imagen (medido el 15-oct, memorias EcoDB a7b3fd95 y 77487c0d)
- `api/Dockerfile` instala apt sin versiones (`curl ffmpeg gosu` + dependencias): un build otro día baja otras. Las
  versiones de la viva están en `deploy/inventario/ecodb-api_apt.txt` (303 paquetes). Fijarlas de verdad exige una
  instantánea de Debian por fecha (snapshot.debian.org): los repos normales borran las versiones viejas.
- Python, medido el 28-oct sin descargar nada: los 174 pins de `api/constraints.txt` son EXACTAMENTE los de la viva
  (0 distintos); en la viva solo hay 2 paquetes sin pin: `ecodb-langchain` (se instala del propio repo) y `pip` (viene
  de la imagen base, fijada por digest; la capa 3 lo subió a 26.2). O sea: lo que hoy no es reproducible es apt, no
  Python. Confirmarlo con un build en frío vuelve a bajar varios GB de torch + CUDA: decisión de Pepe pendiente
  (FarOS, decisión 87).
