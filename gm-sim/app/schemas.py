from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any

class TeamBase(BaseModel):
    name: str
    abbr: str
    conference: Optional[str] = None
    division: Optional[str] = None
    elo: Optional[float] = 1500
    scheme_off: Optional[str] = None
    scheme_def: Optional[str] = None
    cap_space: Optional[int] = 0
    cap_year: Optional[int] = 2027

class TeamCreate(TeamBase):
    pass

class TeamRead(TeamBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

class PlayerBase(BaseModel):
    name: str
    pos: str
    team_id: Optional[int] = None
    age: Optional[int] = None
    height: Optional[int] = None
    weight: Optional[int] = None
    ovr: Optional[int] = None
    pot: Optional[int] = None
    spd: Optional[int] = None
    acc: Optional[int] = None
    agi: Optional[int] = None
    str: Optional[int] = None
    awr: Optional[int] = None
    injury_status: Optional[str] = "OK"
    morale: Optional[int] = 50
    stamina: Optional[int] = 80
    thp: Optional[int] = None
    tha_s: Optional[int] = None
    tha_m: Optional[int] = None
    tha_d: Optional[int] = None
    tup: Optional[int] = None
    rel: Optional[int] = None
    rr: Optional[int] = None
    cth: Optional[int] = None
    cit: Optional[int] = None
    pbk: Optional[int] = None
    rbk: Optional[int] = None
    iblk: Optional[int] = None
    oblk: Optional[int] = None
    mcv: Optional[int] = None
    zcv: Optional[int] = None
    prs: Optional[int] = None
    pmv: Optional[int] = None
    fmv: Optional[int] = None
    bsh: Optional[int] = None
    purs: Optional[int] = None

class PlayerCreate(PlayerBase):
    pass

class PlayerRead(PlayerBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class ContractBase(BaseModel):
    player_id: int
    team_id: int
    sign_year: int
    years: int
    total_value: int
    guaranteed: int
    y1_cap: int
    y1_dead: int
    y2_cap: Optional[int] = None
    y2_dead: Optional[int] = None
    y3_cap: Optional[int] = None
    y3_dead: Optional[int] = None

class ContractCreate(ContractBase):
    pass

class ContractRead(ContractBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class DepthChartBase(BaseModel):
    team_id: int
    pos_group: str
    slot: int
    player_id: int
    snap_pct_plan: float

class DepthChartCreate(DepthChartBase):
    pass

class DepthChartRead(DepthChartBase):
    model_config = ConfigDict(from_attributes=True)

class DraftPickBase(BaseModel):
    year: int
    round: int
    overall: int
    owned_by_team_id: int
    original_team_id: int
    jj_value: Optional[int] = None
    alt_value: Optional[int] = None

class DraftPickCreate(DraftPickBase):
    pass

class DraftPickRead(DraftPickBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class TransactionBase(BaseModel):
    type: str
    team_from: Optional[int] = None
    team_to: Optional[int] = None
    payload_json: Any
    cap_delta_from: Optional[int] = None
    cap_delta_to: Optional[int] = None

class TransactionCreate(TransactionBase):
    pass

class TransactionRead(TransactionBase):
    id: int
    timestamp: Any
    model_config = ConfigDict(from_attributes=True)

class GameBase(BaseModel):
    season: int
    week: int
    home_team_id: int
    away_team_id: int
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    sim_seed: Optional[int] = None
    box_json: Optional[Any] = None
    injuries_json: Optional[Any] = None

class GameCreate(GameBase):
    pass

class GameRead(GameBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class StandingBase(BaseModel):
    season: int
    team_id: int
    wins: Optional[int] = 0
    losses: Optional[int] = 0
    ties: Optional[int] = 0
    pf: Optional[int] = 0
    pa: Optional[int] = 0
    elo: Optional[float] = 1500

class StandingCreate(StandingBase):
    pass

class StandingRead(StandingBase):
    model_config = ConfigDict(from_attributes=True)
