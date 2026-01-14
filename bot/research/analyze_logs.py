from __future__ import annotations

import json
from pathlib import Path
from typing import List


def load_json_logs(path: Path) -> List[dict]:
    entries = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                entries.append(json.loads(line))
    return entries
