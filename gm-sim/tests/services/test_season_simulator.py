import pytest

from app.services.season import SeasonSimulator, TeamSeed


class StubNarrator:
    async def generate_game_recap(self, context):
        return f"{context['teams']['home']} edges {context['teams']['away']}"


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
