from collections import defaultdict

import pytest

from app.services.injuries import InjuryEvent, PlayerParticipation
from app.services.llm import NarrativeRecap
from app.services.season import SeasonSimulator, TeamSeed


class StubNarrator:
    async def generate_game_recap(self, context):
        return NarrativeRecap(
            summary=f"{context['teams']['home']} edges {context['teams']['away']}",
            facts={
                "summary": "stub",
                "scoreboard": {
                    "home_team": context["teams"]["home"],
                    "away_team": context["teams"]["away"],
                    "home_score": context["score"]["home"],
                    "away_score": context["score"]["away"],
                },
                "notable_players": context.get("key_players", []),
            },
        )


@pytest.mark.asyncio
async def test_season_simulator_runs_round_robin():
    teams = [
        TeamSeed(id=1, name="Kansas City Chiefs", abbr="KC", rating=92.0),
        TeamSeed(id=2, name="Dallas Cowboys", abbr="DAL", rating=90.0),
        TeamSeed(id=3, name="Buffalo Bills", abbr="BUF", rating=91.0),
        TeamSeed(id=4, name="San Francisco 49ers", abbr="SF", rating=93.0),
    ]
    simulator = SeasonSimulator(teams, narrative_client=StubNarrator(), rng_seed=123)
    games = await simulator.simulate_season()

    assert len(games) == 6
    assert all(
        game.recap.startswith("Kansas")
        or game.recap.startswith("Dallas")
        or game.recap.startswith("Buffalo")
        or game.recap.startswith("San")
        for game in games
    )
    standings = simulator.standings()
    assert set(standings.keys()) == {1, 2, 3, 4}
    total_games = sum(team.wins + team.losses + team.ties for team in standings.values())
    assert total_games == len(games) * 2
    for log in games:
        assert log.drives
        assert log.headline

    player_stats = simulator.player_stats()
    assert all(player_stats[team_id] for team_id in player_stats)
    sample_line = player_stats[1][0]
    assert sample_line.player
    assert sample_line.week >= 1


@pytest.mark.asyncio
async def test_nfl_schedule_generates_seventeen_games():
    teams = []
    team_id = 1
    for conference in ("AFC", "NFC"):
        for division in ("East", "North", "South", "West"):
            for slot in range(4):
                teams.append(
                    TeamSeed(
                        id=team_id,
                        name=f"{conference} {division} {slot}",
                        abbr=f"{conference[0]}{division[0]}{slot}",
                        rating=80 + slot + (5 if conference == "AFC" else 0),
                        conference=conference,
                        division=division,
                    )
                )
                team_id += 1

    simulator = SeasonSimulator(teams, narrative_client=None, rng_seed=7)

    assert 17 <= len(simulator.schedule) <= 20

    game_counts: defaultdict[int, int] = defaultdict(int)
    division_members: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    for team in teams:
        division_members[(team.conference, team.division)].append(team.id)

    for week in simulator.schedule:
        seen: set[int] = set()
        for home, away in week:
            assert home not in seen
            assert away not in seen
            seen.update({home, away})
            game_counts[home] += 1
            game_counts[away] += 1

    assert all(count == 17 for count in game_counts.values())

    # Divisional opponents meet home and away (two games total).
    for members in division_members.values():
        for idx, team_a in enumerate(members):
            for team_b in members[idx + 1 :]:
                total_meetings = sum(
                    1
                    for week in simulator.schedule
                    for home, away in week
                    if {home, away} == {team_a, team_b}
                )
                assert total_meetings == 2


class StubInjuryEngine:
    def __init__(self) -> None:
        self.calls = 0

    def team_availability_penalty(self, roster):
        return 0.0

    def simulate_game(self, team_id, participants):
        self.calls += 1
        if not participants:
            return []
        participant = participants[0]
        participant.injury_weeks_remaining = 1
        return [
            InjuryEvent(
                player_id=participant.player_id,
                team_id=team_id,
                severity="minor",
                weeks_out=1,
                occurred_snap=10,
                injury_type="Hamstring pull",
            )
        ]

    def rest_week(self, rosters):
        for roster in rosters.values():
            for participant in roster:
                if participant.injury_weeks_remaining > 0:
                    participant.injury_weeks_remaining -= 1


@pytest.mark.asyncio
async def test_season_simulator_tracks_injuries():
    teams = [
        TeamSeed(id=1, name="Team A", abbr="A", rating=92.0),
        TeamSeed(id=2, name="Team B", abbr="B", rating=90.0),
    ]
    rosters = {
        1: [PlayerParticipation(player_id=101, position="QB", snaps=60)],
        2: [PlayerParticipation(player_id=201, position="QB", snaps=60)],
    }
    simulator = SeasonSimulator(
        teams,
        narrative_client=None,
        rng_seed=42,
        injury_engine=StubInjuryEngine(),
        rosters=rosters,
    )
    games = await simulator.simulate_season()
    assert games
    assert any(game.injuries for game in games)
    assert simulator.injuries()


def _result(home_score: int, away_score: int, *, headline: str = "Test showdown") -> dict:
    return {
        "home_score": home_score,
        "away_score": away_score,
        "win_prob": 0.5,
        "drives": [
            {"team": "home", "result": "TD", "yards": 65, "minutes": 3.1},
            {"team": "away", "result": "FG", "yards": 45, "minutes": 2.2},
        ],
        "headline": headline,
        "player_stats": {"home": [], "away": []},
    }


@pytest.mark.asyncio
async def test_head_to_head_tiebreak_prioritises_direct_results(monkeypatch):
    outcomes = iter(
        [
            _result(31, 20),  # 1 beats 4
            _result(28, 17),  # 2 beats 3
            _result(24, 20),  # 3 beats 1
            _result(17, 21),  # 4 beats 2
            _result(27, 23),  # 1 beats 2
            _result(30, 21),  # 3 beats 4
        ]
    )

    def fake_simulate_game(*args, **kwargs):
        return next(outcomes)

    monkeypatch.setattr("app.services.season.simulate_game", fake_simulate_game)
    teams = [
        TeamSeed(id=1, name="Team One", abbr="ONE", rating=92.0),
        TeamSeed(id=2, name="Team Two", abbr="TWO", rating=91.0),
        TeamSeed(id=3, name="Team Three", abbr="THR", rating=91.5),
        TeamSeed(id=4, name="Team Four", abbr="FOU", rating=90.0),
    ]
    simulator = SeasonSimulator(teams, narrative_client=None, rng_seed=1)
    await simulator.simulate_season()
    ranking = [team.id for team in simulator.ranked_teams()]
    assert ranking[:2] == [3, 1]


@pytest.mark.asyncio
async def test_playoffs_follow_seed_order(monkeypatch):
    outcomes = iter(
        [
            _result(31, 20),  # regular season games begin
            _result(28, 17),
            _result(24, 20),
            _result(17, 21),
            _result(27, 23),
            _result(30, 21),
            _result(34, 14),  # semifinal 1
            _result(17, 13),  # semifinal 2
            _result(24, 20),  # championship
        ]
    )

    def fake_simulate_game(*args, **kwargs):
        return next(outcomes)

    monkeypatch.setattr("app.services.season.simulate_game", fake_simulate_game)
    teams = [
        TeamSeed(id=1, name="Team One", abbr="ONE", rating=92.0),
        TeamSeed(id=2, name="Team Two", abbr="TWO", rating=91.0),
        TeamSeed(id=3, name="Team Three", abbr="THR", rating=91.5),
        TeamSeed(id=4, name="Team Four", abbr="FOU", rating=90.0),
    ]
    simulator = SeasonSimulator(teams, narrative_client=None, rng_seed=1)
    await simulator.simulate_season()
    postseason_logs = await simulator.simulate_playoffs(seeds=4)
    assert len(postseason_logs) == 3
    assert all(log.stage == "postseason" for log in postseason_logs)
    assert postseason_logs[0].round_name == "Conference Championship"
    assert postseason_logs[-1].round_name == "Super Bowl"
    assert simulator.postseason_games() == postseason_logs
