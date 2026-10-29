# Autoheal — runbook de despliegue y verificación

> **Qué cierra**: action item #1 del post-mortem `Faro/Informes/Postmortem/2026-08-21_embeddings_outage.md`.
> El 19-ago (día 170) embeddings se colgó ~50 min sin auto-recuperarse: teníamos
> healthcheck (detección) pero `restart: unless-stopped` no reinicia por `unhealthy`,
> solo por EXIT. Autoheal añade la mitad de acción que faltaba.
>
> **Estado**: STAGED, NO aplicado. Aprobado por Pepe (día 170). Se aplica y se
> verifica **con Pepe presente y en baja carga** — el paso de aplicar recrea el
> contenedor embeddings (~180s de reload de modelo = save/search KO ese rato), y la
> verificación honesta tumba embeddings a propósito unos ~5 min.
>
> **Artefacto**: `docker-compose.autoheal.yml` (overlay inerte, solo embeddings).

## Precondición
- Pepe presente (es un cambio de infra sobre la memoria compartida viva).
- Baja carga: nadie guardando/buscando en EcoDB durante ~5-6 min.
- Anunciar en la sala familia: "voy a tumbar embeddings para probar autoheal, ~5 min sin memoria".

## 1. Aplicar

```powershell
cd %USERPROFILE%\Documents\EcoDB
docker compose -f docker-compose.yml -f docker-compose.autoheal.yml up -d
```

Esto: (a) levanta `ecodb-autoheal`, (b) **recrea** `ecodb-embeddings` para añadirle el
label `autoheal=true`. Espera a que embeddings vuelva `healthy` (start_period 180s).

Comprobar:
```powershell
docker ps --filter name=ecodb-autoheal --format "{{.Names}} {{.Status}}"   # Up
docker inspect --format '{{json .Config.Labels.autoheal}}' ecodb-embeddings # "true"
docker logs --tail 20 ecodb-autoheal                                        # "Monitoring containers for unhealthy status"
```

## 2. Verificar DE VERDAD (unhealthy controlado)

No basta con que arranque. Hay que provocar el estado real del incidente —proceso vivo
pero sin servir— y ver que autoheal lo reinicia solo. Se simula congelando el proceso
(igual que hizo la GPU pegada) con SIGSTOP:

```powershell
# 1. Congelar embeddings (proceso vivo, health empieza a fallar)
docker kill --signal=SIGSTOP ecodb-embeddings

# 2. Observar la transición a unhealthy (~150s: retries 10 x interval 15s) y el reinicio
docker events --filter container=ecodb-embeddings --filter event=health_status --filter event=restart
#   → esperado: health_status: unhealthy  →  (autoheal) restart

# 3. Confirmar recuperación
docker ps --filter name=ecodb-embeddings --format "{{.Status}}"   # Up (healthy) tras el reload
```

Verificación E2E final (la que vale): un `search` y un `save_memory` reales desde una
sesión de agente devuelven OK. **Solo entonces está "hecho".**

> Nota: si SIGSTOP no bastara (el reinicio de un proceso congelado a veces necesita
> SIGKILL para la parada grácil), autoheal usa `docker restart`, que hace stop+start;
> `AUTOHEAL_DEFAULT_STOP_TIMEOUT=30` da margen y tras él va SIGKILL. Verificar en el log.

## 3. Rollback

```powershell
docker rm -f ecodb-autoheal
# El label autoheal=true en embeddings es inerte sin el contenedor autoheal; se puede dejar.
# Para quitarlo del todo: docker compose up -d --force-recreate embeddings (sin el overlay).
```

## 4. Números honestos (qué mejora y qué no)

- **Antes**: cuelgue → `unhealthy` para siempre → hasta que un humano tropieza. MTTD ~50 min (medido el día 170).
- **Con autoheal**: `unhealthy` (~150s de healthcheck) → autoheal reinicia en ≤10s → reload de modelo ~180s. **Recuperación desatendida ≈ 5,5 min.** Enorme mejora, **no instantáneo**: la detección primera sigue siendo los ~150s del healthcheck de Docker.
- Autoheal da la **acción**. NO da **alerta**: nadie se entera de que hubo un reinicio. Eso es el action item #2 — `WEBHOOK_URL` de autoheal apuntando a un receptor que avise a la familia (relay/EcoDB). Es el MTTD de verdad. Pendiente aparte.

## 5. Caveats

1. **Docker Desktop en Windows (riesgo específico del entorno de Pepe)**: el montaje
   `/var/run/docker.sock:/var/run/docker.sock` funciona en Docker Desktop porque el
   demonio Linux expone el socket en la VM, pero **hay que verificarlo en la máquina de
   Pepe** — es la razón principal por la que esto se verifica en su entorno, no a ciegas.
   Si el socket no montara, autoheal arranca pero no ve contenedores (`docker logs`
   lo diría).
2. **Restart-loop**: si embeddings fallara de forma persistente (no transitoria),
   autoheal lo reiniciaría en bucle cada vez que va `unhealthy`. Es ruidoso pero no peor
   que quedarse caído — y es en sí una señal. El webhook (#2) lo convierte en alerta.
3. **Seguridad**: autoheal tiene control total de Docker por el socket (puede parar/reiniciar
   cualquier contenedor). Es inherente a la herramienta y es el patrón oficial. Alcance
   limitado a un solo contenedor por el label.
4. **Alcance quirúrgico**: solo embeddings. Extender a `AUTOHEAL_CONTAINER_LABEL=all`
   (todo el stack con healthcheck: api, ner, postgres, worker, cell) es el action item #5,
   aún sin aprobar. Decidir con Pepe tras ver funcionar este.

## 6. En la misma ventana: la caché de GPU del embedder (L47, #547, 29-oct)

La imagen de autoheal va fijada por digest (la `latest` del 21-ago que ya está en disco; la etiqueta
`latest` de Docker Hub se republicó el 29-oct). El cambio de `embeddings/server.py` (`_release_cache`)
reinicia embeddings igual que el paso 1, así que va en la misma ventana, ANTES de aplicar el overlay:

```powershell
# medir ANTES: 200 embeds seguidos y la GPU después
nvidia-smi --query-gpu=memory.used --format=csv
docker tag ecodb-embeddings:0.2.5 ecodb-embeddings:0.2.5-pre547
docker build -f deploy/overlays/Dockerfile.overlay547-emb -t ecodb-embeddings:0.2.5 .
# (el paso 1 recrea embeddings con la imagen nueva y el label)
# medir DESPUÉS: la misma ráfaga; la memoria usada debe volver a la base, no crecer
```
Vuelta atrás: `docker tag ecodb-embeddings:0.2.5-pre547 ecodb-embeddings:0.2.5` y recrear embeddings.

---
*Primera mano: mecanismo de willfarrell/autoheal verificado en su repo (github.com/willfarrell/docker-autoheal)
el 2026-08-21. Config de embeddings leída de `docker-compose.yml:60-96`.*
