from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    DateTime,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    abbr = Column(String, nullable=False, unique=True)
    conference = Column(String)
    division = Column(String)
    elo = Column(Float, default=1500)
    scheme_off = Column(String)
    scheme_def = Column(String)
    cap_space = Column(Integer, default=0)
    cap_year = Column(Integer, default=2027)
    players = relationship("Player", back_populates="team")


class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    pos = Column(String, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    age = Column(Integer)
    height = Column(Integer)
    weight = Column(Integer)
    ovr = Column(Integer)
    pot = Column(Integer)
    spd = Column(Integer)
    acc = Column(Integer)
    agi = Column(Integer)
    str = Column(Integer)
    awr = Column(Integer)
    injury_status = Column(String, default="OK")
    morale = Column(Integer, default=50)
    stamina = Column(Integer, default=80)
    # Positional skills
    thp = Column(Integer)
    tha_s = Column(Integer)
    tha_m = Column(Integer)
    tha_d = Column(Integer)
    tup = Column(Integer)
    rel = Column(Integer)
    rr = Column(Integer)
    cth = Column(Integer)
    cit = Column(Integer)
    pbk = Column(Integer)
    rbk = Column(Integer)
    iblk = Column(Integer)
    oblk = Column(Integer)
    mcv = Column(Integer)
    zcv = Column(Integer)
    prs = Column(Integer)
    pmv = Column(Integer)
    fmv = Column(Integer)
    bsh = Column(Integer)
    purs = Column(Integer)
    team = relationship("Team", back_populates="players")


class Contract(Base):
    __tablename__ = "contracts"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    start_year = Column(Integer, nullable=False)
    end_year = Column(Integer, nullable=False)
    apy = Column(Integer, nullable=False)
    base_salary_yearly = Column(JSON, nullable=False)
    signing_bonus_total = Column(Integer, default=0, nullable=False)
    guarantees_total = Column(Integer, default=0, nullable=False)
    cap_hits_yearly = Column(JSON, nullable=False)
    dead_money_yearly = Column(JSON, nullable=False)
    no_trade = Column(Boolean, default=False, nullable=False)
    void_years = Column(Integer, default=0, nullable=False)


class DepthChart(Base):
    __tablename__ = "depth_chart"
    team_id = Column(Integer, ForeignKey("teams.id"), primary_key=True)
    pos_group = Column(String, primary_key=True)
    slot = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    snap_pct_plan = Column(Float)


class DraftPick(Base):
    __tablename__ = "draft_picks"
    id = Column(Integer, primary_key=True)
    year = Column(Integer)
    round = Column(Integer)
    overall = Column(Integer)
    owned_by_team_id = Column(Integer, ForeignKey("teams.id"))
    original_team_id = Column(Integer, ForeignKey("teams.id"))
    jj_value = Column(Integer)
    alt_value = Column(Integer)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, server_default=func.now())
    type = Column(String)
    team_from = Column(Integer, ForeignKey("teams.id"))
    team_to = Column(Integer, ForeignKey("teams.id"))
    payload_json = Column(JSON)
    cap_delta_from = Column(Integer)
    cap_delta_to = Column(Integer)


class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True)
    season = Column(Integer)
    week = Column(Integer)
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))
    home_score = Column(Integer)
    away_score = Column(Integer)
    sim_seed = Column(Integer)
    box_json = Column(JSON)
    injuries_json = Column(JSON)


class Standing(Base):
    __tablename__ = "standings"
    season = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), primary_key=True)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    ties = Column(Integer, default=0)
    pf = Column(Integer, default=0)
    pa = Column(Integer, default=0)
    elo = Column(Float, default=1500)


class PracticeSquad(Base):
    __tablename__ = "practice_squad"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, unique=True)
    international_pathway = Column(Boolean, default=False, nullable=False)
    elevations = Column(Integer, default=0, nullable=False)
    ps_ir = Column(Boolean, default=False, nullable=False)


class GamedayRoster(Base):
    __tablename__ = "gameday_rosters"
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    actives = Column(JSON, nullable=False)
    inactives = Column(JSON, nullable=False)
    elevated_player_ids = Column(JSON, nullable=False, default=list)
    ol_count = Column(Integer, nullable=False)
    valid = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("game_id", "team_id", name="uq_gameday_team_game"),
    )


class RosterRule(Base):
    __tablename__ = "roster_rules"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(Integer, nullable=False)


class SalaryCap(Base):
    __tablename__ = "salary_cap"
    id = Column(Integer, primary_key=True)
    league_year = Column(Integer, unique=True, nullable=False)
    cap_base = Column(Integer, nullable=False)
    rollover_by_team = Column(JSON, default=dict, nullable=False)


class PlayerGameStat(Base):
    __tablename__ = "player_game_stats"

    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    season = Column(Integer, nullable=False)
    week = Column(Integer, nullable=False)
    stats = Column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint("game_id", "player_id", name="uq_stats_game_player"),
    )


class PlayerSeasonStat(Base):
    __tablename__ = "player_season_stats"

    id = Column(Integer, primary_key=True)
    season = Column(Integer, nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    games_played = Column(Integer, default=0, nullable=False)
    stats = Column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint("season", "player_id", name="uq_stats_season_player"),
    )


class TeamSeasonStat(Base):
    __tablename__ = "team_season_stats"

    id = Column(Integer, primary_key=True)
    season = Column(Integer, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    games_played = Column(Integer, default=0, nullable=False)
    stats = Column(JSON, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("season", "team_id", name="uq_team_season"),)
