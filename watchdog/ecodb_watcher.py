"""EcoDB file watcher — Task 4.12.
Watches configured directories for file changes.
Registers new/modified docs via API. Soft-deletes removed docs.
Runs on host via Task Scheduler or manual start.

State format: {filepath: {hash: str, document_id: str | null}}
Storing document_id in state avoids URI-lookup on delete.
"""
import hashlib
import json
import logging
import os
import time

import requests

log = logging.getLogger("ecodb.watcher")

# Config from env
WATCH_DIRS = os.environ.get("ECODB_WATCH_DIRS", "").split(";")
WATCH_EXTENSIONS = set(
    os.environ.get(
        "ECODB_WATCH_EXTENSIONS",
        ".pdf,.txt,.md,.docx,.html,.mp3,.wav,.m4a,.ogg,.flac",
    ).split(",")
)
API_URL = os.environ.get("ECODB_API_URL", "http://localhost:8080").rstrip("/")
API_KEY = os.environ["ECODB_API_KEY"]
POLL_INTERVAL = int(os.environ.get("ECODB_POLL_INTERVAL", "60"))
PROJECT_ID = int(os.environ.get("ECODB_DEFAULT_PROJECT_ID", "1"))
STATE_FILE = os.environ.get("ECODB_WATCHER_STATE", "watcher_state.json")

EXCLUDE_PATTERNS = {
    "node_modules", ".git", "__pycache__", ".env",
    ".tmp", ".lock", ".obsidian",
}

_EXT_TO_DOCTYPE = {
    ".pdf": "pdf", ".docx": "docx", ".doc": "docx",
    ".html": "html", ".htm": "html",
    ".md": "md", ".markdown": "markdown",
    ".txt": "txt", ".text": "txt",
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio",
    ".ogg": "audio", ".flac": "audio", ".mp4": "audio",
}

_token: str | None = None
_token_expires_at: float = 0.0


def _get_token() -> str:
    global _token, _token_expires_at
    now = time.time()
    if _token and now < _token_expires_at - 30:
        return _token
    resp = requests.post(f"{API_URL}/auth/token", json={"api_key": API_KEY}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    _token = data["access_token"]
    # JWT TTL from response or default 3600s
    _token_expires_at = now + float(data.get("expires_in", 3600))
    return _token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _should_watch(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    if any(p in EXCLUDE_PATTERNS for p in parts):
        return False
    ext = os.path.splitext(path)[1].lower()
    return ext in WATCH_EXTENSIONS


def _scan_directories() -> dict[str, str]:
    """Scan watch dirs. Returns {filepath: hash}."""
    files: dict[str, str] = {}
    for d in WATCH_DIRS:
        d = d.strip()
        if not d or not os.path.isdir(d):
            continue
        for root, dirs, filenames in os.walk(d):
            dirs[:] = [x for x in dirs if x not in EXCLUDE_PATTERNS]
            for fname in filenames:
                fpath = os.path.join(root, fname)
                if _should_watch(fpath):
                    try:
                        files[fpath] = _file_hash(fpath)
                    except (OSError, PermissionError):
                        pass
    return files


def _load_state() -> dict[str, dict]:
    """State: {filepath: {hash: str, document_id: str | null}}"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            raw = json.load(f)
        # Migrate legacy format {filepath: hash_str} → new format
        migrated = {}
        for k, v in raw.items():
            if isinstance(v, str):
                migrated[k] = {"hash": v, "document_id": None}
            else:
                migrated[k] = v
        return migrated
    return {}


def _save_state(state: dict[str, dict]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _register_document(fpath: str) -> str | None:
    """POST /documents. Returns document_id or None on failure."""
    ext = os.path.splitext(fpath)[1].lower()
    doc_type = _EXT_TO_DOCTYPE.get(ext, "txt")
    try:
        resp = requests.post(
            f"{API_URL}/documents",
            headers=_headers(),
            json={
                "uri": fpath,
                "filename": os.path.basename(fpath),
                "doc_type": doc_type,
                "project_id": PROJECT_ID,
                "workspace_id": 1,
            },
            timeout=30,
        )
        if resp.status_code in (200, 201):
            doc_id = str(resp.json().get("id", ""))
            log.info("Registered: %s → %s", fpath, doc_id)
            return doc_id
        elif resp.status_code == 409:
            # Already exists — reindex by looking up existing id
            existing = resp.json().get("document_id")
            if existing:
                _reindex_document(existing)
                return existing
            log.info("Already exists (no id in 409): %s", fpath)
        else:
            log.warning("Failed to register %s: %d %s", fpath, resp.status_code, resp.text[:200])
    except Exception as e:
        log.error("Error registering %s: %s", fpath, e)
    return None


def _reindex_document(document_id: str) -> None:
    """PUT /documents/{id}/reindex."""
    try:
        resp = requests.put(
            f"{API_URL}/documents/{document_id}/reindex",
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code == 200:
            log.info("Reindexed: %s", document_id)
        else:
            log.warning("Reindex failed for %s: %d", document_id, resp.status_code)
    except Exception as e:
        log.error("Error reindexing %s: %s", document_id, e)


def _delete_document(document_id: str, fpath: str) -> None:
    """DELETE /documents/{id} — soft delete."""
    try:
        resp = requests.delete(
            f"{API_URL}/documents/{document_id}",
            headers=_headers(),
            timeout=15,
        )
        if resp.status_code in (200, 204):
            log.info("Soft-deleted: %s (was %s)", document_id, fpath)
        else:
            log.warning("Delete failed for %s: %d", document_id, resp.status_code)
    except Exception as e:
        log.error("Error deleting %s: %s", document_id, e)


def poll_and_sync() -> None:
    prev_state = _load_state()
    current_files = _scan_directories()
    new_state: dict[str, dict] = {}

    # New or modified files
    for fpath, fhash in current_files.items():
        prev = prev_state.get(fpath)
        prev_hash = prev["hash"] if prev else None
        prev_doc_id = prev["document_id"] if prev else None

        if prev_hash != fhash:
            if prev_doc_id:
                # File changed — reindex existing doc
                log.info("Modified: %s", fpath)
                _reindex_document(prev_doc_id)
                new_state[fpath] = {"hash": fhash, "document_id": prev_doc_id}
            else:
                # New file
                log.info("New file: %s", fpath)
                doc_id = _register_document(fpath)
                new_state[fpath] = {"hash": fhash, "document_id": doc_id}
        else:
            # Unchanged
            new_state[fpath] = prev

    # Deleted files
    for fpath, entry in prev_state.items():
        if fpath not in current_files:
            doc_id = entry.get("document_id") if isinstance(entry, dict) else None
            if doc_id:
                log.info("Deleted: %s", fpath)
                _delete_document(doc_id, fpath)
            else:
                log.info("File removed (no document_id tracked): %s", fpath)

    _save_state(new_state)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    log.info("Watcher starting. Dirs: %s", WATCH_DIRS)
    log.info("Extensions: %s", sorted(WATCH_EXTENSIONS))
    while True:
        try:
            poll_and_sync()
        except Exception as e:
            log.error("Poll cycle error: %s", e)
        time.sleep(POLL_INTERVAL)
