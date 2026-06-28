"""轻量历史记录：把每次生成/分析的结果追加到本地 JSONL，便于回看。

服务器端持久化，单文件、自动只保留最近 N 条。失败均静默（不影响主流程）。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

MAX_ITEMS = 50


def _file() -> Path:
    p = os.environ.get("HISTORY_FILE") or str(
        Path.home() / ".ai-test-copilot" / "history.jsonl"
    )
    return Path(p)


def add(mode: str, title: str, input_text: str, result: dict) -> str:
    """追加一条记录，返回其 id。"""
    rec = {
        "id": uuid.uuid4().hex[:12],
        "ts": int(time.time()),
        "mode": mode,  # generate | analyze
        "title": title,
        "input": input_text,
        "result": result,
    }
    try:
        items = _load()
        items.append(rec)
        items = items[-MAX_ITEMS:]
        f = _file()
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass
    except OSError:
        pass
    return rec["id"]


def _load() -> list[dict]:
    f = _file()
    if not f.is_file():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def list_meta() -> list[dict]:
    """返回元信息（不含完整结果），最新在前。"""
    items = _load()
    items.reverse()
    return [{"id": i["id"], "ts": i["ts"], "mode": i["mode"], "title": i["title"]} for i in items]


def get(item_id: str) -> dict | None:
    for i in _load():
        if i["id"] == item_id:
            return i
    return None
