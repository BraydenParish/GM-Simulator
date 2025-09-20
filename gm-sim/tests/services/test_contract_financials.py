import math

from app.schemas import ContractSignRequest
from app.services.contracts import build_contract_financials


def test_build_contract_financials_proration() -> None:
    request = ContractSignRequest(
        player_id=1,
        team_id=1,
        start_year=2025,
        end_year=2027,
        base_salary_yearly={2025: 1_000_000, 2026: 2_000_000, 2027: 3_000_000},
        signing_bonus_total=9_000_000,
        guarantees_total=6_000_000,
        void_years=1,
    )

    financials = build_contract_financials(request)

    assert math.isclose(financials.apy, 5_000_000.0)
    assert financials.cap_hits == {
        2025: 3_250_000,
        2026: 4_250_000,
        2027: 5_250_000,
    }
    assert financials.dead_money[2025] == 10_000_000
    assert financials.dead_money[2026] == 8_750_000
    assert financials.dead_money[2027] == 7_500_000
    assert financials.dead_money[2028] == 2_250_000


def test_build_contract_financials_zero_bonus() -> None:
    request = ContractSignRequest(
        player_id=2,
        team_id=1,
        start_year=2025,
        end_year=2026,
        base_salary_yearly={2025: 2_000_000, 2026: 2_500_000},
        signing_bonus_total=0,
        guarantees_total=2_000_000,
    )

    financials = build_contract_financials(request)

    assert financials.cap_hits == {2025: 2_000_000, 2026: 2_500_000}
    assert financials.dead_money[2025] == 2_000_000
    assert financials.dead_money[2026] == 0
