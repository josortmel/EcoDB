"""Download LongMemEval-S and convert sessions to Markdown files for Docling ingestion."""
import json
import os
import sys
import urllib.request

DATA_URL = "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions_md")


def download():
    os.makedirs(DATA_DIR, exist_ok=True)
    dest = os.path.join(DATA_DIR, "longmemeval_s_cleaned.json")
    if os.path.exists(dest):
        print(f"Already downloaded: {dest}")
        return dest
    print(f"Downloading LongMemEval-S from {DATA_URL}...")
    urllib.request.urlretrieve(DATA_URL, dest)
    print(f"Saved to {dest}")
    return dest


def convert_sessions(json_path: str):
    """Convert haystack_sessions from the FIRST entry to individual Markdown files.

    LongMemEval-S shares the same haystack across all queries,
    so we only need the sessions from entry[0].
    """
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    entry = data[0]
    sessions = entry["haystack_sessions"]
    session_ids = entry["haystack_session_ids"]
    dates = entry["haystack_dates"]

    os.makedirs(SESSIONS_DIR, exist_ok=True)

    for i, (sess, sid, date) in enumerate(zip(sessions, session_ids, dates)):
        md_lines = [
            f"# Session: {sid}",
            "",
            f"**Date:** {date}",
            "",
            "---",
            "",
        ]
        for turn in sess:
            role = turn["role"].capitalize()
            content = turn["content"]
            md_lines.append(f"**{role}:** {content}")
            md_lines.append("")

        filename = f"session_{i:03d}.md"
        filepath = os.path.join(SESSIONS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

    print(f"Converted {len(sessions)} sessions to {SESSIONS_DIR}/")
    return len(sessions)


def main():
    json_path = download()
    n = convert_sessions(json_path)
    print(f"\nReady. {n} session files in {SESSIONS_DIR}/")
    print("Next: run ingest_sessions.py to load into EcoDB")


if __name__ == "__main__":
    main()
