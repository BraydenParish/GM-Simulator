import builtins
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


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
    rookie_year: int | None = None
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


class InjuryDetail(BaseModel):
    id: int
    player_id: int
    player_name: str
    team_id: int
    team_name: str | None
    game_id: int | None
    injury_type: str
    severity: str
    expected_weeks_out: int
    occurred_at: datetime | None


class InjuryListResponse(BaseModel):
    items: List[InjuryDetail]
    total: int


class TeamHealthSummary(BaseModel):
    team_id: int
    team_name: str
    active_injuries: int
    severe_injuries: int
    average_fatigue: float | None
    high_fatigue_players: int


class TeamHealthSummaryResponse(BaseModel):
    items: List[TeamHealthSummary]


class TradeNarrative(BaseModel):
    summary: str
    team_positions: Dict[str, str]
    negotiation_points: List[str]


class TradeEvaluationRequest(BaseModel):
    team_a_name: str
    team_b_name: str
    team_a_assets: List[int] = Field(default_factory=list)
    team_b_assets: List[int] = Field(default_factory=list)
    include_narrative: bool = False
    narrative_focus: str | None = None
    tasks_completed: str | None = None
    tasks_remaining: str | None = None

    @field_validator("team_a_assets", "team_b_assets", mode="before")
    @classmethod
    def _coerce_int_assets(cls, value: Any) -> List[int]:
        if value is None:
            return []
        if isinstance(value, list):
            return [int(item) for item in value]
        raise TypeError("trade assets must be provided as a list of pick overalls")


class TradeEvaluationResponse(BaseModel):
    team_a_value: int
    team_b_value: int
    delta: int
    narrative: TradeNarrative | None = None


class FreeAgentNarrative(BaseModel):
    summary: str
    team_pitch: str
    player_reaction: str
    next_steps: List[str]


class FreeAgentNegotiationMetrics(BaseModel):
    apy: float
    guaranteed_percentage: float
    signing_bonus_proration: float
    market_delta: float | None = None
    risk_flags: List[str] = Field(default_factory=list)


class FreeAgentNegotiationRequest(BaseModel):
    team_name: str
    player_name: str
    player_position: str
    player_age: int | None = Field(default=None, ge=18, le=55)
    offer_years: int = Field(gt=0, le=7)
    offer_total_value: int = Field(gt=0)
    signing_bonus: int = Field(default=0, ge=0)
    guarantees: int | None = Field(default=None, ge=0)
    incentives: List[str] = Field(default_factory=list)
    player_market_apy: float | None = Field(default=None, ge=0)
    include_narrative: bool = True
    tasks_completed: str | None = None
    tasks_remaining: str | None = None

    @field_validator("guarantees")
    @classmethod
    def _validate_guarantees(cls, value: int | None, info: ValidationInfo) -> int | None:
        if value is None:
            return None
        total_value = info.data.get("offer_total_value")
        if total_value is not None and value > total_value:
            raise ValueError("guarantees cannot exceed total contract value")
        return value

    @field_validator("incentives", mode="before")
    @classmethod
    def _coerce_incentives(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            cleaned: List[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    cleaned.append(item.strip())
            return cleaned
        raise TypeError("incentives must be provided as a list of strings")


class FreeAgentNegotiationResponse(BaseModel):
    team_name: str
    player_name: str
    metrics: FreeAgentNegotiationMetrics
    narrative: FreeAgentNarrative | None = None


class ContractSignRequest(BaseModel):
    player_id: int
    team_id: int
    start_year: int
    end_year: int
    base_salary_yearly: dict[int, int]
    signing_bonus_total: int
    guarantees_total: int
    no_trade: bool = False
    void_years: int = 0

    @field_validator("base_salary_yearly", mode="before")
    @classmethod
    def _coerce_int_keys(cls, value: Any) -> dict[int, int]:
        if isinstance(value, dict):
            return {int(k): int(v) for k, v in value.items()}
        raise TypeError("base_salary_yearly must be a mapping of year to salary")

    @field_validator("end_year")
    @classmethod
    def _validate_years(cls, end_year: int, info: ValidationInfo) -> int:
        start_year = info.data.get("start_year")
        if start_year is not None and end_year < start_year:
            raise ValueError("end_year must be greater than or equal to start_year")
        return end_year

    @field_validator("base_salary_yearly")
    @classmethod
    def _validate_schedule(cls, schedule: dict[int, int], info: ValidationInfo) -> dict[int, int]:
        start_year = info.data.get("start_year")
        end_year = info.data.get("end_year")
        if start_year is None or end_year is None:
            return schedule
        expected_years = set(range(start_year, end_year + 1))
        if set(schedule) != expected_years:
            raise ValueError("base_salary_yearly must provide entries for each contract year")
        return schedule


class ContractRead(BaseModel):
    id: int
    player_id: int
    team_id: int
    start_year: int
    end_year: int
    apy: float
    base_salary_yearly: dict[int, int]
    signing_bonus_total: int
    guarantees_total: int
    cap_hits_yearly: dict[int, int]
    dead_money_yearly: dict[int, int]
    no_trade: bool = False
    void_years: int = 0

    model_config = ConfigDict(from_attributes=True)

    @field_validator("base_salary_yearly", "cap_hits_yearly", "dead_money_yearly", mode="before")
    @classmethod
    def _coerce_schedule(cls, value: Any) -> dict[int, int]:
        if isinstance(value, dict):
            return {int(k): int(v) for k, v in value.items()}
        return value


class ContractCutRequest(BaseModel):
    contract_id: int
    league_year: int
    post_june1: bool = False


class ContractCutResponse(BaseModel):
    contract_id: int
    league_year: int
    dead_money_current_year: int
    dead_money_next_year: int
    cap_savings: int
    team_cap_space: int


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


class DraftClassGenerationRequest(BaseModel):
    year: int = Field(ge=1900, le=2100)
    rounds: int = Field(default=7, ge=1, le=10)
    players_per_round: int = Field(default=32, ge=1, le=64)
    seed: int | None = None
    position_weights: Dict[str, float] | None = None
    base_overall: float = Field(default=68.0, ge=40.0, le=95.0)
    overall_stddev: float = Field(default=7.5, gt=0, le=20)

    @field_validator("position_weights")
    @classmethod
    def _validate_weights(cls, value: Dict[str, float] | None) -> Dict[str, float] | None:
        if value is None:
            return None
        cleaned: Dict[str, float] = {}
        total = 0.0
        for pos, weight in value.items():
            try:
                weight_val = float(weight)
            except (TypeError, ValueError) as exc:
                raise ValueError("position weight must be numeric") from exc
            if weight_val <= 0:
                raise ValueError("position weights must be positive")
            cleaned[pos.upper()] = weight_val
            total += weight_val
        if total <= 0:
            raise ValueError("position weights must sum to a positive value")
        return cleaned


class DraftClassGenerationResponse(BaseModel):
    year: int
    total: int
    items: List[PlayerRead]


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


class PracticeSquadEntryBase(BaseModel):
    team_id: int
    player_id: int
    international_pathway: bool = False
    ps_ir: bool = False


class PracticeSquadAssignRequest(PracticeSquadEntryBase):
    pass


class PracticeSquadEntryRead(PracticeSquadEntryBase):
    id: int
    elevations: int = 0

    model_config = ConfigDict(from_attributes=True)


class GamedayRosterSetRequest(BaseModel):
    game_id: int
    team_id: int
    actives: List[int]
    inactives: List[int]
    elevated_player_ids: List[int] = Field(default_factory=list)


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


class RosterRuleRead(BaseModel):
    id: int
    key: str
    value: Any

    model_config = ConfigDict(from_attributes=True)
