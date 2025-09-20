from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, DateTime, JSON, PrimaryKeyConstraint
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
    player_id = Column(Integer, ForeignKey("players.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    sign_year = Column(Integer)
    years = Column(Integer)
    total_value = Column(Integer)
    guaranteed = Column(Integer)
    y1_cap = Column(Integer)
    y1_dead = Column(Integer)
    y2_cap = Column(Integer)
    y2_dead = Column(Integer)
    y3_cap = Column(Integer)
    y3_dead = Column(Integer)

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
