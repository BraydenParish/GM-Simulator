from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any, Dict


class ErrorResponse(BaseModel):
    detail: Any


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
    injury_status: str = "OK"
    morale: Optional[int] = 50
    stamina: Optional[int] = 80
    pbp_rating: Optional[float] = None
    madden_rating: Optional[float] = None
    pff_grade: Optional[float] = None
    blended_rating: Optional[float] = None
    rating_confidence: Optional[float] = None
    rating_components: Optional[Dict[str, Dict[str, float]]] = None
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
    injury_status: str = "OK"
    model_config = ConfigDict(from_attributes=True)


class PlayerListResponse(BaseModel):
    items: List[PlayerRead]
    total: int
    page: int
    page_size: int


class PracticeSquadBase(BaseModel):
    team_id: int
    player_id: int
    international_pathway: bool = False
    elevations: int = 0
    ps_ir: bool = False


class PracticeSquadRead(PracticeSquadBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class PracticeSquadAssignRequest(BaseModel):
    team_id: int
    player_id: int
    international_pathway: bool = False
    ps_ir: bool = False


class GamedaySetActivesRequest(BaseModel):
    game_id: int
    team_id: int
    actives: List[int]
    inactives: List[int]
    elevated_player_ids: List[int] = []


class GamedayRosterRead(BaseModel):
    id: int
    game_id: int
    team_id: int
    actives: List[int]
    inactives: List[int]
    elevated_player_ids: List[int]
    ol_count: int
    valid: bool

    model_config = ConfigDict(from_attributes=True)


class RosterRuleBase(BaseModel):
    key: str
    value: int


class RosterRuleRead(RosterRuleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ContractRead(BaseModel):
    id: int
    player_id: int
    team_id: int
    start_year: int
    end_year: int
    apy: int
    base_salary_yearly: Dict[str, int]
    signing_bonus_total: int
    guarantees_total: int
    cap_hits_yearly: Dict[str, int]
    dead_money_yearly: Dict[str, int]
    no_trade: bool = False
    void_years: int = 0

    model_config = ConfigDict(from_attributes=True)


class ContractSignRequest(BaseModel):
    player_id: int
    team_id: int
    start_year: int
    end_year: int
    base_salary_yearly: Dict[int, int]
    signing_bonus_total: int = 0
    guarantees_total: int = 0
    no_trade: bool = False
    void_years: int = 0


class ContractCutRequest(BaseModel):
    player_id: int
    team_id: int
    league_year: int
    post_june1: bool = False


class ContractCutResponse(BaseModel):
    dead_money_current: int
    dead_money_future: int
    cap_space: int
    freed_cap: int


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


class PlayerGameStatRead(BaseModel):
    id: int
    game_id: int
    player_id: int
    team_id: int
    season: int
    week: int
    stats: Dict[str, int]

    model_config = ConfigDict(from_attributes=True)


class TeamGameStatRead(BaseModel):
    id: int
    game_id: int
    team_id: int
    season: int
    week: int
    stats: Dict[str, int]

    model_config = ConfigDict(from_attributes=True)


class PlayerSeasonStatRead(BaseModel):
    id: int
    season: int
    player_id: int
    team_id: int
    games_played: int
    stats: Dict[str, int]

    model_config = ConfigDict(from_attributes=True)


class TeamSeasonStatRead(BaseModel):
    id: int
    season: int
    team_id: int
    games_played: int
    stats: Dict[str, int]

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
