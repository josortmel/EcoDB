#!/usr/bin/env bash
# Runs the api and mcp test suites the way CI does (#1362), so home and CI see the same thing.
#
#   MIN_TESTS=690 OUT=test-results bash scripts/ci/tests_api.sh
#
# From the repo ROOT (the migrations open sql/ by relative path). Needs a throwaway test database
# (docker-compose.testdb.yml; TEST_DB_HOST/TEST_DB_PORT) and the light test dependencies
# (pip install -r api/requirements-test.txt -c api/constraints.txt). Never the live family DB:
# conftest.py refuses it.
#
# - One pytest process PER FILE: several files keep app/pool state at module level, and the whole folder
#   in one process ends in «Event loop is closed». Each file is judged on its own.
# - Fake embeddings/NER services (api/tests/servicios_falsos.py) instead of the real ones: without them
#   every test that saves a memory gets a 503 that is not its fault.
# - The API rate limits go up for the run: with instant fake services the suite saves more than 20
#   memories a minute (POST /memories has its own limit, RATE_LIMIT_CREATE_MEMORY; test_decisiones_vigentes
#   got 429s). At home it only passed because each save waited 3 s for the missing NER service.
#   test_multitenant still checks the rate-limit headers.
# - Fails closed: a file that does not exit 0, or fewer tests than MIN_TESTS, is red. A green without a
#   count does not count.
set -uo pipefail

MIN_TESTS="${MIN_TESTS:-0}"
OUT="${OUT:-test-results}"
FAKE_PORT="${FAKE_PORT:-8090}"
mkdir -p "$OUT"

python -m uvicorn servicios_falsos:app --app-dir api/tests --host 127.0.0.1 --port "$FAKE_PORT" \
    --log-level warning &
FAKE_PID=$!
trap 'kill "$FAKE_PID" 2>/dev/null' EXIT

ready=0
for _ in $(seq 1 50); do
    if python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:$FAKE_PORT/health', timeout=1)" \
        2>/dev/null; then ready=1; break; fi
    sleep 0.2
done
if [ "$ready" != 1 ]; then
    echo "::error::the fake services did not start on port $FAKE_PORT"
    exit 1
fi

export EMBEDDINGS_URL="http://127.0.0.1:$FAKE_PORT"
export NER_SERVICE_URL="http://127.0.0.1:$FAKE_PORT"
export RATE_LIMIT_DEFAULT=1000000
export RATE_LIMIT_SEARCH=1000000
export RATE_LIMIT_CREATE_MEMORY=1000000
export RATE_LIMIT_PREVIEW=1000000

shopt -s nullglob  # a folder without tests adds nothing (a literal «test_*.py» would reach pytest)
files=(api/tests/test_*.py mcp/tests/test_*.py)
if [ "${#files[@]}" -eq 0 ]; then
    echo "::error::no test files found (run from the repo root)"
    exit 1
fi

failed_files=()
for f in "${files[@]}"; do
    name="$(basename "$(dirname "$(dirname "$f")")")_$(basename "$f" .py)"
    python -m pytest "$f" -q -p no:cacheprovider --junitxml="$OUT/$name.xml" > "$OUT/$name.log" 2>&1
    rc=$?
    echo "$name rc=$rc $(tail -n 1 "$OUT/$name.log")"
    if [ "$rc" -ne 0 ]; then failed_files+=("$name"); fi
done

python - "$OUT" "$MIN_TESTS" <<'PY'
import glob, sys, xml.etree.ElementTree as ET

out, minimum = sys.argv[1], int(sys.argv[2])
totals = dict(tests=0, failures=0, errors=0, skipped=0)
for path in glob.glob(f"{out}/*.xml"):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.get(key, 0))
print("tests run: {tests} (minimum {m}) · failures {failures} · errors {errors} · skipped {skipped}".format(
    m=minimum, **totals))
if totals["tests"] < minimum:
    print(f"::error::only {totals['tests']} tests ran (expected at least {minimum})")
    sys.exit(1)
PY
count_rc=$?

if [ "${#failed_files[@]}" -gt 0 ]; then
    echo "::error::red files: ${failed_files[*]}"
    exit 1
fi
exit "$count_rc"
