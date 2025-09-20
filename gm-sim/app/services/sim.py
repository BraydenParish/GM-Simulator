from app.services.ratings import compute_team_rating
from app.services.elo import win_prob
import random


def simulate_game(
    home_team_id: int,
    away_team_id: int,
    home_rating: float,
    away_rating: float,
    seed: int = None,
):
    if seed is not None:
        random.seed(seed)
    prob = win_prob(home_rating, away_rating)
    exp_pts = 45
    home_pts = int(exp_pts * prob + random.gauss(0, 3))
    away_pts = int(exp_pts * (1 - prob) + random.gauss(0, 3))
    box = {
        "home_qb": {
            "yds": random.randint(180, 320),
            "td": random.randint(1, 3),
            "int": random.randint(0, 2),
        },
        "away_qb": {
            "yds": random.randint(180, 320),
            "td": random.randint(1, 3),
            "int": random.randint(0, 2),
        },
        "home_wr": {"yds": random.randint(40, 120), "td": random.randint(0, 2)},
        "away_wr": {"yds": random.randint(40, 120), "td": random.randint(0, 2)},
        "home_edge": {"sacks": random.randint(0, 3)},
        "away_edge": {"sacks": random.randint(0, 3)},
    }
    return {
        "home_score": home_pts,
        "away_score": away_pts,
        "win_prob": prob,
        "box": box,
    }
