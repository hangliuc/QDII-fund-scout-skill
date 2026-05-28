from __future__ import annotations

import json
from pathlib import Path

from core.models import FundDataResult

COMPACT_FIELDS = {
    "code", "name", "short_name", "return_1y",
    "purchase_status", "purchase_limit", "effectively_closed",
    "total_fee", "scale",
}


def format(data: FundDataResult, output_path: str, compact: bool = False) -> str:
    result = data.to_dict()
    if compact:
        result["funds"] = [
            {k: v for k, v in fund.items() if k in COMPACT_FIELDS}
            for fund in result["funds"]
        ]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
