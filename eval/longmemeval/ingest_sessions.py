"""Ingest LongMemEval session MDs into EcoDB via the document API.

Creates workspace 'longmemeval' + project 'benchmark' if they don't exist.
Registers each session MD as a document for Docling ingestion.
The worker accesses files via /benchmark-data/ inside the container
(bind-mounted via docker-compose.benchmark.yml).
"""
import glob
import json
import os
import sys
import time

import httpx

API_URL = os.environ.get("ECODB_API_URL", "http://localhost:8080")
API_KEY = os.environ.get("ECODB_API_KEY", "")
SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions_md")
CONTAINER_DATA_PATH = "/benchmark-data"

if not API_KEY:
    print("ERROR: Set ECODB_API_KEY environment variable")
    sys.exit(1)


def headers():
    return {"Authorization": f"Bearer {API_KEY}"}


def get_or_create_workspace(client: httpx.Client) -> int:
    r = client.get(f"{API_URL}/workspaces", headers=headers())
    r.raise_for_status()
    for ws in r.json():
        if ws["name"] == "longmemeval":
            print(f"Workspace 'longmemeval' exists (id={ws['id']})")
            return ws["id"]
    r = client.post(f"{API_URL}/workspaces", headers=headers(),
                     json={"name": "longmemeval"})
    r.raise_for_status()
    ws_id = r.json()["id"]
    print(f"Created workspace 'longmemeval' (id={ws_id})")
    return ws_id


def get_or_create_project(client: httpx.Client, workspace_id: int) -> int:
    r = client.get(f"{API_URL}/workspaces/{workspace_id}/projects", headers=headers())
    r.raise_for_status()
    for proj in r.json().get("projects", r.json() if isinstance(r.json(), list) else []):
        if isinstance(proj, dict) and proj.get("name") == "benchmark":
            print(f"Project 'benchmark' exists (id={proj['id']})")
            return proj["id"]
    r = client.post(f"{API_URL}/workspaces/{workspace_id}/projects", headers=headers(),
                     json={"name": "benchmark"})
    r.raise_for_status()
    proj_id = r.json()["id"]
    print(f"Created project 'benchmark' (id={proj_id})")
    return proj_id


def ingest_sessions(client: httpx.Client, workspace_id: int, project_id: int):
    md_files = sorted(glob.glob(os.path.join(SESSIONS_DIR, "session_*.md")))
    if not md_files:
        print(f"ERROR: No session files in {SESSIONS_DIR}. Run prepare_data.py first.")
        sys.exit(1)

    print(f"Ingesting {len(md_files)} sessions...")

    doc_ids = []
    for md_path in md_files:
        filename = os.path.basename(md_path)
        container_path = f"{CONTAINER_DATA_PATH}/{filename}"

        r = client.post(f"{API_URL}/documents", headers=headers(),
                         json={
                             "uri": container_path,
                             "filename": filename,
                             "doc_type": "markdown",
                             "workspace_id": workspace_id,
                             "project_id": project_id,
                         })
        r.raise_for_status()
        doc_id = r.json()["id"]
        doc_ids.append({"filename": filename, "doc_id": doc_id})
        print(f"  Registered: {filename} -> {doc_id}")

    mapping_path = os.path.join(os.path.dirname(__file__), "data", "doc_id_mapping.json")
    with open(mapping_path, "w") as f:
        json.dump(doc_ids, f, indent=2)
    print(f"\nDoc ID mapping saved to {mapping_path}")
    return doc_ids


def wait_for_ingestion(client: httpx.Client, doc_ids: list, timeout: int = 900):
    print(f"\nWaiting for Docling ingestion (timeout={timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        statuses = {}
        for entry in doc_ids:
            r = client.get(f"{API_URL}/documents/{entry['doc_id']}", headers=headers())
            r.raise_for_status()
            statuses[entry["doc_id"]] = r.json()["status"]

        indexed = sum(1 for s in statuses.values() if s == "indexed")
        failed = sum(1 for s in statuses.values() if s == "failed")
        pending = len(doc_ids) - indexed - failed

        if pending == 0:
            print(f"\nIngestion complete: {indexed} indexed, {failed} failed")
            return indexed, failed

        elapsed = int(time.time() - start)
        print(f"  {elapsed}s: {indexed} indexed, {failed} failed, {pending} pending")
        time.sleep(15)

    print(f"\nERROR: Timeout after {timeout}s")
    return 0, len(doc_ids)


def main():
    with httpx.Client(timeout=30) as client:
        ws_id = get_or_create_workspace(client)
        proj_id = get_or_create_project(client, ws_id)
        print(f"Workspace={ws_id}, Project={proj_id}")

        config_path = os.path.join(os.path.dirname(__file__), "data", "benchmark_config.json")
        with open(config_path, "w") as f:
            json.dump({"workspace_id": ws_id, "project_id": proj_id}, f)
        print(f"Config saved to {config_path}")

        doc_ids = ingest_sessions(client, ws_id, proj_id)
        indexed, failed = wait_for_ingestion(client, doc_ids)
        if failed > 0:
            print(f"WARNING: {failed} documents failed ingestion")
        print(f"\nReady for benchmark.")


if __name__ == "__main__":
    main()
