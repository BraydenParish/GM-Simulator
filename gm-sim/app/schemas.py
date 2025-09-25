import builtins
from typing import Any, List, Optional

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


class InjuryReportRead(BaseModel):
    id: int
    season: int
    week: int
    team_id: int
    team_abbr: Optional[str] = None
    player_id: int
    player_name: Optional[str] = None
    severity: str
    weeks_out: int
    occurred_snap: Optional[int] = None
    injury_type: str
    expected_return_week: Optional[int] = None


class InjuryReportList(BaseModel):
    season: int
    week: Optional[int] = None
    team_id: Optional[int] = None
    injuries: List[InjuryReportRead]


class PlayoffGameRead(BaseModel):
    round_number: int
    round_name: str
    matchup: int
    home_team_id: int
    home_seed: int
    home_team: str
    away_team_id: int
    away_seed: int
    away_team: str
    home_score: int
    away_score: int
    winner_team_id: int
    winner_seed: int
    headline: str
    narrative_recap: Optional[str] = None


class ChampionSummary(BaseModel):
    team_id: int
    seed: int
    name: str
    abbr: str


class PlayoffSimulationResponse(BaseModel):
    season: int
    bracket_size: int
    generated_narratives: bool
    games: List[PlayoffGameRead]
    champion: ChampionSummary


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
    narrative_recap: Optional[str] = None
    narrative_facts: Optional[Any] = None


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


class FreeAgentSummary(BaseModel):
    player_id: int
    name: str
    pos: str
    age: Optional[int] = None
    overall: Optional[int] = None
    stamina: Optional[int] = None


class FreeAgentProjectionRead(BaseModel):
    season: int
    name: str
    pos: Optional[str] = None
    tier: Optional[str] = None
    expected_market: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None
    player_id: Optional[int] = None
    overall: Optional[int] = None
    age: Optional[int] = None
    current_team_id: Optional[int] = None
    current_team_abbr: Optional[str] = None


class FreeAgentSigningPlan(BaseModel):
    player_id: int
    team_id: int
    start_year: int
    years: int
    total_value: int
    signing_bonus: int = 0
    guarantees_total: Optional[int] = None
    void_years: int = 0
    no_trade: bool = False

    @field_validator("years")
    @classmethod
    def _validate_years(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("years must be positive")
        return value


class FreeAgentSigningResponse(BaseModel):
    contract: ContractRead
    team_cap_space: int


class UpcomingGameSummary(BaseModel):
    game_id: int
    week: int
    home_team_id: int
    away_team_id: int
    home_team: str
    away_team: str


class GameHighlight(BaseModel):
    game_id: int
    drive_index: int
    descriptor: str
    team: Optional[str] = None
    result: Optional[str] = None
    yards: Optional[int] = None
    clock_minutes: Optional[float] = None


class GameSummaryWithHighlights(BaseModel):
    game_id: int
    season: int
    week: int
    home_team_id: int
    away_team_id: int
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    narrative_recap: Optional[str] = None
    highlights: List[GameHighlight]


class StandingSnapshot(BaseModel):
    team_id: int
    team_name: str
    team_abbr: str
    wins: int
    losses: int
    ties: int
    points_for: int
    points_against: int
    elo: Optional[float] = None


class SeasonProgressSummary(BaseModel):
    season: int
    scheduled_weeks: int
    scheduled_games: int
    games_played: int
    completed_weeks: int
    next_week: Optional[int] = None
    last_completed_week: Optional[int] = None
    season_over: bool


class SeasonDashboardResponse(BaseModel):
    progress: SeasonProgressSummary
    upcoming_games: List[UpcomingGameSummary]
    standings: List[StandingSnapshot]
    recent_games: List[GameSummaryWithHighlights]
    free_agent_targets: List[FreeAgentProjectionRead]
    available_free_agents: List[FreeAgentSummary]
