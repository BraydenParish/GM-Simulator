def win_prob(home_rating: float, away_rating: float, hfa: float = 55.0) -> float:
    ra = home_rating + hfa
    rb = away_rating
    exp = (rb - ra) / 400.0
    return 1.0 / (1.0 + (10 ** exp))

def apply_result(current_elo: float, expected: float, score: float, k: float = 32.0) -> float:
    return current_elo + k * (score - expected)
