import csv
import os
from typing import Dict, List

_jj_chart = {}
_chart_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "jj_chart.csv")
if os.path.exists(_chart_path):
    with open(_chart_path) as f:
        for row in csv.DictReader(f):
            _jj_chart[int(row["overall"])] = int(row["value"])

def jj_value(pick_overall: int) -> int:
    return _jj_chart.get(pick_overall, 0)

def evaluate_trade(assets_a: List[int], assets_b: List[int]) -> Dict[str, int]:
    # assets are pick overalls for MVP
    total_a = sum(jj_value(p) for p in assets_a)
    total_b = sum(jj_value(p) for p in assets_b)
    return {"team_a": total_a, "team_b": total_b, "delta": total_a - total_b}
