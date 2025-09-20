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
