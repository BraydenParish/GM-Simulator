import builtins
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


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
    team_id: int | None = None
    age: int | None = None
    height: int | None = None
    weight: int | None = None
    ovr: int | None = None
    pot: int | None = None
    spd: int | None = None
    acc: int | None = None
    agi: int | None = None
    str: int | None = None
    awr: int | None = None
    injury_status: builtins.str = Field(default="OK")
    morale: int | None = 50
    stamina: int | None = 80
    thp: int | None = None
    tha_s: int | None = None
    tha_m: int | None = None
    tha_d: int | None = None
    tup: int | None = None
    rel: int | None = None
    rr: int | None = None
    cth: int | None = None
    cit: int | None = None
    pbk: int | None = None
    rbk: int | None = None
    iblk: int | None = None
    oblk: int | None = None
    mcv: int | None = None
    zcv: int | None = None
    prs: int | None = None
    pmv: int | None = None
    fmv: int | None = None
    bsh: int | None = None
    purs: int | None = None


class PlayerCreate(PlayerBase):
    pass


class PlayerRead(PlayerBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class PlayerListResponse(BaseModel):
    items: List[PlayerRead]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    detail: str


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
