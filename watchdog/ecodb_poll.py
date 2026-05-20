"""EcoDB one-shot file poller — Task 4.12.

Single scan: detect new/modified/deleted files, sync with API, exit.
Designed for Task Scheduler (run every N minutes) or cron.

Usage:
  ECODB_API_KEY=ecodb_... ECODB_WATCH_DIRS="C:\\Docs;C:\\Notes" python ecodb_poll.py

Config via environment variables — same as ecodb_watcher.py:
  ECODB_WATCH_DIRS         semicolon-separated directories to watch
  ECODB_WATCH_EXTENSIONS   comma-separated extensions (default: .pdf,.txt,.md,...)
  ECODB_API_URL            API base URL (default: http://localhost:8080)
  ECODB_API_KEY            API key (required)
  ECODB_DEFAULT_PROJECT_ID project_id for new documents (default: 1)
  ECODB_WATCHER_STATE      path to state JSON file (default: watcher_state.json)
"""
import logging
import sys

# Reuse all logic from ecodb_watcher — no duplication.
from ecodb_watcher import poll_and_sync, WATCH_DIRS, WATCH_EXTENSIONS, STATE_FILE

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    log = logging.getLogger("ecodb.poll")
    log.info("One-shot poll. Dirs: %s | Extensions: %s | State: %s",
             WATCH_DIRS, sorted(WATCH_EXTENSIONS), STATE_FILE)
    try:
        poll_and_sync()
        log.info("Poll complete.")
    except Exception as e:
        log.error("Poll failed: %s", e)
        sys.exit(1)
