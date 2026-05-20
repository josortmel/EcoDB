#!/usr/bin/env bash
# runtime_1_8_1_9.sh — Tests de integración: embeddings service
# Tarea 1.8 (local PyTorch INT8) + Tarea 1.9 (cloud Jina API fallback)
#
# Uso: ./runtime_1_8_1_9.sh [PORT]
# Puerto default: 8090 (EXPOSE en Dockerfile)
#
# Cloud tests (TC1-TC5) solo se ejecutan si el backend reporta "cloud".
# Para testear cloud: reiniciar container con EMBEDDING_BACKEND=cloud + JINA_API_KEY.
# Para forzar TC4 (key inválida): JINA_API_KEY=invalid_key_for_testing + EMBEDDING_BACKEND=cloud.

PORT="${1:-8090}"
BASE="http://localhost:$PORT"
PASS=0
FAIL=0
SKIP=0

# 32×32 PNG rojo — mínimo que Jina v4 encode_image acepta (1×1 falla con "broken data stream")
TINY_PNG="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAANUlEQVR4nO3QsQ0AMAzDsLT//9yeoCkbeYAN6LzZdZf3x0GSKEmUJEoSJYmSREmiJFGSaMoHo8QBPwYSAhsAAAAASUVORK5CYII="

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; NC='\033[0m'

# Detectar comando Python disponible (python3 en Linux, python en Windows/Git Bash)
PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo "")
if [[ -z "$PYTHON" ]]; then echo "ERROR: python no encontrado en PATH"; exit 2; fi

pass() { echo -e "${GREEN}PASS${NC} [$1] $2"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}FAIL${NC} [$1] $2 | esperado: $3 | obtenido: $4"; FAIL=$((FAIL+1)); }
skip() { echo -e "${YELLOW}SKIP${NC} [$1] $2 — $3"; SKIP=$((SKIP+1)); }
section() { echo -e "\n=== $1 ==="; }

# Extrae campo JSON escalar con python (sin dependencia jq)
jq_val() {
    "$PYTHON" -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('$1',''))" 2>/dev/null
}
jq_len() {
    "$PYTHON" -c "import sys,json; d=json.loads(sys.stdin.read()); v=d.get('$1',[]); print(len(v))" 2>/dev/null
}

echo "INFO: BASE = $BASE"

# Detectar backend desde /health para condicionar secciones TT/TI/TC
HEALTH_INIT=$(curl -s --max-time 5 "$BASE/health" 2>/dev/null)
BACKEND=$(echo "$HEALTH_INIT" | jq_val "backend")
echo "INFO: backend = ${BACKEND:-<sin respuesta — servicio no disponible>}"

if [[ -z "$BACKEND" ]]; then
    echo -e "${RED}ERROR${NC}: servicio no responde en $BASE/health — ¿container levantado?"
    exit 2
fi

# ============================================================
section "TH — Health checks"
# ============================================================

# TH1: GET /health — status ok + model_loaded=True
RESP=$(curl -s -w '\n%{http_code}' "$BASE/health")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$HTTP" == "200" ]]; then
    ML=$(echo "$BODY" | jq_val "model_loaded")
    STATUS=$(echo "$BODY" | jq_val "status")
    BKND=$(echo "$BODY" | jq_val "backend")
    if [[ "$ML" == "True" ]]; then
        pass "TH1" "/health → 200 | status=$STATUS backend=$BKND model_loaded=True"
    else
        fail "TH1" "/health model_loaded" "True" "$ML | body: $BODY"
    fi
else
    fail "TH1" "/health HTTP" "200" "$HTTP | body: $BODY"
fi

# TH2: GET /health/detailed — 200 + campos VRAM presentes para local con GPU
RESP=$(curl -s -w '\n%{http_code}' "$BASE/health/detailed")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$HTTP" == "200" ]]; then
    VRAM_T=$(echo "$BODY" | jq_val "vram_total_mib")
    VRAM_U=$(echo "$BODY" | jq_val "vram_used_mib")
    CPU=$(echo "$BODY" | jq_val "cpu_percent")
    RAM=$(echo "$BODY" | jq_val "ram_percent")
    if [[ "$BACKEND" == "local" ]] && [[ "$VRAM_T" == "None" || -z "$VRAM_T" ]]; then
        fail "TH2" "/health/detailed vram_total_mib" ">0 (local + GPU)" "None/vacío — ¿GPU no disponible en container?"
    else
        pass "TH2" "/health/detailed → 200 | vram_total=${VRAM_T}MiB used=${VRAM_U}MiB cpu=${CPU}% ram=${RAM}%"
    fi
else
    fail "TH2" "/health/detailed HTTP" "200" "$HTTP | body: $BODY"
fi

# ============================================================
section "TT — /embed/text (backend local)"
# ============================================================

if [[ "$BACKEND" != "local" ]]; then
    skip "TT1-TT4" "/embed/text local (4 tests)" "backend=$BACKEND, no local"
else

# TT1: texto único, task=retrieval passage, truncate_dim=512 → embedding 512-dim
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' \
  -d '{"texts":["Hola mundo, esto es una prueba de embedding multimodal"],"task":"retrieval","prompt_name":"passage","truncate_dim":512}')
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$HTTP" == "200" ]]; then
    DIMS=$(echo "$BODY" | jq_val "dimensions")
    CNT=$(echo "$BODY" | jq_val "count")
    EMB_LEN=$(echo "$BODY" | jq_len "embeddings")
    DUR=$(echo "$BODY" | jq_val "duration_ms")
    if [[ "$DIMS" == "512" && "$CNT" == "1" && "$EMB_LEN" == "1" ]]; then
        pass "TT1" "/embed/text básico → dim=512 count=1 dur=${DUR}ms"
    else
        fail "TT1" "/embed/text dims/count/emb_len" "512/1/1" "${DIMS}/${CNT}/${EMB_LEN} | $BODY"
    fi
else
    fail "TT1" "/embed/text HTTP" "200" "$HTTP | $BODY"
fi

# TT2: task=retrieval prompt_name=query
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' \
  -d '{"texts":["search query in knowledge graph"],"task":"retrieval","prompt_name":"query"}')
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$HTTP" == "200" ]]; then
    CNT=$(echo "$BODY" | jq_val "count")
    pass "TT2" "/embed/text task=retrieval prompt=query → 200 count=$CNT"
else
    fail "TT2" "/embed/text retrieval+query" "200" "$HTTP | $BODY"
fi

# TT3: task=code
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' \
  -d '{"texts":["def hello_world():\n    return \"hello\""],"task":"code","prompt_name":"passage"}')
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
[[ "$HTTP" == "200" ]] && pass "TT3" "/embed/text task=code → 200" || fail "TT3" "/embed/text task=code" "200" "$HTTP | $BODY"

# TT4: batch de 3 textos, task=text-matching
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' \
  -d '{"texts":["texto uno","texto dos","texto tres"],"task":"text-matching"}')
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$HTTP" == "200" ]]; then
    CNT=$(echo "$BODY" | jq_val "count")
    [[ "$CNT" == "3" ]] && pass "TT4" "/embed/text batch=3 → 200 count=3" || fail "TT4" "batch count" "3" "$CNT | $BODY"
else
    fail "TT4" "/embed/text batch=3 HTTP" "200" "$HTTP | $BODY"
fi

fi  # end BACKEND==local TT

# ============================================================
section "TI — /embed/image (backend local)"
# ============================================================

if [[ "$BACKEND" != "local" ]]; then
    skip "TI1-TI3" "/embed/image local (3 tests)" "backend=$BACKEND, no local"
else

# TI1: data URI base64 1×1 PNG → 200
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/image" \
  -H 'Content-Type: application/json' \
  -d "{\"images\":[\"$TINY_PNG\"],\"task\":\"retrieval\"}")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$HTTP" == "200" ]]; then
    CNT=$(echo "$BODY" | jq_val "count")
    DUR=$(echo "$BODY" | jq_val "duration_ms")
    pass "TI1" "/embed/image data URI base64 → 200 count=$CNT dur=${DUR}ms"
else
    fail "TI1" "/embed/image base64" "200" "$HTTP | $BODY"
fi

# TI2: path local /etc/hosts → 422 (VS2 LFI fix)
# Sin fix: acepta / y llama encode_image → error en model (500)
# Con fix:  rechaza explícitamente → 422
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/image" \
  -H 'Content-Type: application/json' \
  -d '{"images":["/etc/hosts"],"task":"retrieval"}')
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$HTTP" == "422" ]]; then
    pass "TI2" "/embed/image path local → 422 (VS2 LFI fix aplicado)"
elif [[ "$HTTP" == "200" || "$HTTP" == "500" ]]; then
    fail "TI2" "/embed/image path local (VS2)" "422" "$HTTP — VS2 fix NO aplicado | $BODY"
else
    fail "TI2" "/embed/image path local" "422" "$HTTP | $BODY"
fi

# TI3: data:IMAGE/ uppercase → 200 (FIND-1 fix en :0.2.1 normaliza a minúsculas)
# :0.1.0 rechazaba con 422 (case-sensitive). :0.2.1 normaliza → acepta y embedea.
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/image" \
  -H 'Content-Type: application/json' \
  -d "{\"images\":[\"data:IMAGE/PNG;base64,$(echo "$TINY_PNG" | sed 's/data:image\/png;base64,//')\"],\"task\":\"retrieval\"}")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$HTTP" == "200" ]]; then
    pass "TI3" "/embed/image data:IMAGE/ uppercase → 200 (FIND-1 fix: normalización case-insensitive)"
elif [[ "$HTTP" == "422" ]]; then
    fail "TI3" "uppercase data URI (FIND-1 fix)" "200 (normalizado)" "422 — fix NOT applied"
else
    fail "TI3" "uppercase data URI" "200" "$HTTP | $BODY"
fi

fi  # end BACKEND==local TI

# ============================================================
section "TV — Validación pydantic (ambos backends)"
# ============================================================

# TV1: texts=[] — min_length=1 en Field → 422
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' -d '{"texts":[]}')
HTTP=$(echo "$RESP" | tail -1)
[[ "$HTTP" == "422" ]] && pass "TV1" "texts=[] → 422" || fail "TV1" "texts vacío" "422" "$HTTP"

# TV2: texto con null byte (\u0000) → field_validator lo rechaza con 422
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' \
  -d '{"texts":["hello\u0000world"],"task":"retrieval"}')
HTTP=$(echo "$RESP" | tail -1)
[[ "$HTTP" == "422" ]] && pass "TV2" "null byte en texto → 422" || fail "TV2" "null byte" "422" "$HTTP"

# TV3: task inválido → pattern validator → 422
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' \
  -d '{"texts":["test"],"task":"summarize"}')
HTTP=$(echo "$RESP" | tail -1)
[[ "$HTTP" == "422" ]] && pass "TV3" "task=summarize → 422" || fail "TV3" "task inválido" "422" "$HTTP"

# TV4: prompt_name inválido → pattern validator → 422
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' \
  -d '{"texts":["test"],"task":"retrieval","prompt_name":"document"}')
HTTP=$(echo "$RESP" | tail -1)
[[ "$HTTP" == "422" ]] && pass "TV4" "prompt_name=document → 422" || fail "TV4" "prompt_name inválido" "422" "$HTTP"

# TV5: truncate_dim < 64 → 422
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' \
  -d '{"texts":["test"],"truncate_dim":32}')
HTTP=$(echo "$RESP" | tail -1)
[[ "$HTTP" == "422" ]] && pass "TV5" "truncate_dim=32 (<64) → 422" || fail "TV5" "truncate_dim mínimo" "422" "$HTTP"

# TV6: truncate_dim > 2048 → 422
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' \
  -d '{"texts":["test"],"truncate_dim":4096}')
HTTP=$(echo "$RESP" | tail -1)
[[ "$HTTP" == "422" ]] && pass "TV6" "truncate_dim=4096 (>2048) → 422" || fail "TV6" "truncate_dim máximo" "422" "$HTTP"

# TV7: batch texts > MAX_BATCH_TEXT (32) → 422
TEXTS=$("$PYTHON" -c "import json; print(json.dumps({'texts': ['x']*33}))")
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' -d "$TEXTS")
HTTP=$(echo "$RESP" | tail -1)
[[ "$HTTP" == "422" ]] && pass "TV7" "texts batch=33 (>MAX_BATCH_TEXT=32) → 422" || fail "TV7" "batch texto máximo" "422" "$HTTP"

# TV8: batch images > MAX_BATCH_IMAGE (8) → 422
IMGS=$("$PYTHON" -c "import json; print(json.dumps({'images': ['data:image/png;base64,AA==']*9}))")
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/image" \
  -H 'Content-Type: application/json' -d "$IMGS")
HTTP=$(echo "$RESP" | tail -1)
[[ "$HTTP" == "422" ]] && pass "TV8" "images batch=9 (>MAX_BATCH_IMAGE=8) → 422" || fail "TV8" "batch imagen máximo" "422" "$HTTP"

# TV9: /embed/text sin body → 422
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' -d '{}')
HTTP=$(echo "$RESP" | tail -1)
[[ "$HTTP" == "422" ]] && pass "TV9" "/embed/text sin texts → 422" || fail "TV9" "body vacío" "422" "$HTTP"

# ============================================================
section "TC — Cloud backend (solo si BACKEND=cloud)"
# ============================================================

if [[ "$BACKEND" != "cloud" ]]; then
    skip "TC1-TC5" "todos los tests cloud (5 tests)" \
        "backend=$BACKEND. Reiniciar con EMBEDDING_BACKEND=cloud + JINA_API_KEY."
else

# TC1: path local → 422 con mensaje explicativo (_embed_image_cloud)
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/image" \
  -H 'Content-Type: application/json' \
  -d '{"images":["/etc/hosts"],"task":"retrieval"}')
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$HTTP" == "422" ]]; then
    MSG=$(echo "$BODY" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print(d.get('detail','')[:100])" 2>/dev/null)
    pass "TC1" "/embed/image cloud + path local → 422 | detail: $MSG"
else
    fail "TC1" "/embed/image cloud path local" "422" "$HTTP | $BODY"
fi

# TC2: data:IMAGE/ uppercase → 422 en cloud (misma restricción que local)
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/image" \
  -H 'Content-Type: application/json' \
  -d '{"images":["data:IMAGE/PNG;base64,AA=="],"task":"retrieval"}')
HTTP=$(echo "$RESP" | tail -1)
[[ "$HTTP" == "422" ]] \
    && pass "TC2" "cloud: data:IMAGE/ uppercase → 422" \
    || fail "TC2" "cloud uppercase URI" "422" "$HTTP"

# TC3: task=code + prompt_name=passage → prompt_name silenciosamente ignorado, 200
# _map_task_for_cloud: task=code → siempre 'code.query', sin importar prompt_name.
RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
  -H 'Content-Type: application/json' \
  -d '{"texts":["def foo(): pass"],"task":"code","prompt_name":"passage"}')
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -1)
if [[ "$HTTP" == "200" ]]; then
    pass "TC3" "task=code + prompt_name=passage → 200 (prompt_name silenciosamente ignorado — OBS-A confirmado)"
elif [[ "$HTTP" == "502" ]]; then
    fail "TC3" "cloud code+passage" "200" "502 — upstream error | $BODY"
else
    fail "TC3" "cloud code+passage" "200" "$HTTP | $BODY"
fi

# TC4: JINA_API_KEY inválida → upstream 401 → 502 del servicio
# Solo si JINA_API_KEY=invalid_key_for_testing (set manualmente para este test)
if [[ "${JINA_API_KEY:-}" == "invalid_key_for_testing" ]]; then
    RESP=$(curl -s -w '\n%{http_code}' -X POST "$BASE/embed/text" \
      -H 'Content-Type: application/json' \
      -d '{"texts":["test"],"task":"retrieval"}')
    HTTP=$(echo "$RESP" | tail -1)
    BODY=$(echo "$RESP" | head -1)
    [[ "$HTTP" == "502" ]] \
        && pass "TC4" "JINA_API_KEY inválida → 502 upstream" \
        || fail "TC4" "key inválida" "502" "$HTTP | $BODY"
else
    skip "TC4" "key inválida → 502" \
        "JINA_API_KEY no es 'invalid_key_for_testing'. Set env var en container para este test."
fi

# TC5: /health cloud → model_loaded=True incluso si cloud no alcanzable (OBS-B liveness vs readiness)
RESP=$(curl -s "$BASE/health")
ML=$(echo "$RESP" | jq_val "model_loaded")
[[ "$ML" == "True" ]] \
    && pass "TC5" "/health cloud → model_loaded=True (liveness, no readiness — OBS-B documentado)" \
    || fail "TC5" "/health cloud model_loaded" "True" "$ML"

fi  # end BACKEND==cloud TC

# ============================================================
echo -e "\n=============================="
TOTAL=$((PASS+FAIL+SKIP))
echo -e "TOTAL: $TOTAL | ${GREEN}PASS: $PASS${NC} | ${RED}FAIL: $FAIL${NC} | ${YELLOW}SKIP: $SKIP${NC}"
echo "=============================="
if [[ $FAIL -gt 0 ]]; then
    echo "RESULTADO: FAIL"
    exit 1
else
    echo "RESULTADO: PASS (incluyendo $SKIP skipped)"
    exit 0
fi
