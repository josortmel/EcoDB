"""Measure EcoDB search latency across all golden set queries."""
import httpx
import yaml
import time
import os
import statistics
from pathlib import Path

API_URL = "http://localhost:8080"
with open(Path(__file__).parent / "queries.yaml", encoding="utf-8") as f:
    queries = yaml.safe_load(f)["queries"]

key = os.environ.get("ECODB_API_KEY", "")
headers = {"Authorization": f"Bearer {key}"} if key else {}

latencies = []
with httpx.Client() as client:
    for q in queries:
        query_text = q["query"]
        start = time.monotonic()
        try:
            r = client.post(
                f"{API_URL}/search",
                json={"query_text": query_text, "limit": 5},
                headers=headers,
                timeout=30,
            )
            elapsed = (time.monotonic() - start) * 1000
            latencies.append(elapsed)
            print(f"  {query_text[:40]:40s} {elapsed:.0f}ms")
        except Exception as e:
            print(f"  {query_text[:40]:40s} ERROR: {e}")

if latencies:
    s = sorted(latencies)
    n = len(s)
    print(f"\n--- Latency Summary ({n} queries) ---")
    print(f"p50:  {s[n//2]:.0f}ms")
    print(f"p95:  {s[int(n*0.95)]:.0f}ms")
    print(f"p99:  {s[int(n*0.99)]:.0f}ms")
    print(f"min:  {min(s):.0f}ms")
    print(f"max:  {max(s):.0f}ms")
    print(f"mean: {statistics.mean(s):.0f}ms")
