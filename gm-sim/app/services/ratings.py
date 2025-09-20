from typing import Dict, Any

POS_WEIGHTS = dict(QB=0.30, WR=0.12, OT=0.10, EDGE=0.10, CB=0.10,
                   IDL=0.06, LB=0.05, S=0.05, IOL=0.05, RB=0.03, TE=0.04)
DEPTH_WEIGHTS = [1.00, 0.85, 0.70, 0.40]

def apply_injury_and_fatigue(value: float, injury: str, stamina: int) -> float:
    inj_mult = 0.7 if injury != "OK" else 1.0
    fat_mult = 0.5 + (stamina / 200.0)
    return value * inj_mult * fat_mult

# Placeholder: expects players_by_pos_group: Dict[str, List[dict]]
def compute_unit_strength(team_id: int, players_by_pos_group: Dict[str, list]) -> Dict[str, float]:
    unit_strength = {}
    for pos_group, players in players_by_pos_group.items():
        total = 0.0
        for i, player in enumerate(players[:4]):
            weight = DEPTH_WEIGHTS[i]
            ovr = player.get("ovr", 0)
            injury = player.get("injury_status", "OK")
            stamina = player.get("stamina", 80)
            total += weight * apply_injury_and_fatigue(ovr, injury, stamina)
        unit_strength[pos_group] = total
    return unit_strength

def compute_team_rating(team_id: int, unit_strength: Dict[str, float]) -> float:
    rating = 0.0
    for pos, weight in POS_WEIGHTS.items():
        rating += unit_strength.get(pos, 0) * weight
    return rating
