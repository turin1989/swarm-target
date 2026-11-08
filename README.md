# swarm-target: inventory service

A small FastAPI + SQLite inventory service. It is the target codebase for a
coding-swarm benchmark: the backlog in `backlog/tasks.yaml` is mirrored as
GitHub issues labelled `swarm-task`.

## Run

```sh
pip install -e .[dev]
INVENTORY_DB=inventory.db uvicorn inventory.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive API.

## Test

```sh
python -m pytest -q
```

Or without a local Python 3.12:

```sh
docker run --rm -v "$PWD:/app" -w /app python:3.12-slim \
  sh -c 'pip install -q -e .[dev] && python -m pytest -q'
```

## Layout

```
src/inventory/
  models.py          pydantic schemas
  db.py              sqlite connection + schema
  api.py             HTTP routes
  main.py            app factory / entry point
  services/
    stock.py         stock levels and movements
    reports.py       low-stock and valuation reports
    search.py        item search
tests/               pytest suite
backlog/             tasks.yaml + issue creation script
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST/GET | `/items` | create / list items |
| GET/PUT/DELETE | `/items/{id}` | read / update / delete an item |
| GET | `/items/{id}/stock` | stock levels per location + total |
| POST/GET | `/locations` | create / list locations |
| GET | `/locations/{id}` | read a location |
| POST/GET | `/movements` | record / list stock movements (receive, ship, transfer) |
| GET | `/reports/low-stock` | items below their reorder point |
| GET | `/reports/value` | total stock value |
| GET | `/search?q=` | search items by sku/name |
| GET | `/health` | liveness |
