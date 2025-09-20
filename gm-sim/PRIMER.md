# PRIMER

## What
- Add regression coverage for `GET /players/` and implement a paginated response envelope with filters.
- Fix async session lifecycle management and serialize ORM entities into `PlayerRead` DTOs.
- Align the `/players` OpenAPI error example with FastAPI's validation payload and tune dev dependencies/formatting config.
- Document repository structure and the refreshed players endpoint contract.

## Why
- `/players/` previously returned a 500 due to improper dependency wiring and response serialization; the new tests guard against regressions.
- Pagination and filtering are foundational for building higher-level front-end and simulation workflows.
- Updated documentation keeps future tasks aligned with the evolving API surface area.

## Proof
- `pytest -q`
- `ruff check .`
- `black --check .`
- `mypy app`
