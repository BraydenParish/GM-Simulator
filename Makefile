dev:
	poetry run uvicorn app.main:app --reload

seed:
	poetry run python -m app.seed
