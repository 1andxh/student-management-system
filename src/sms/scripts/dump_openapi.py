"""Prints the API's OpenAPI schema as JSON, straight from the FastAPI app.

The frontend generates its TypeScript API types from this (web/, `npm run
gen:api`), so frontend types can't silently drift from the Pydantic
schemas. Reading it from the app object instead of a running server's
/openapi.json means generation needs no server, no Docker and no database:
building the app only constructs the SQLAlchemy engine, which doesn't
connect until the first query. CI regenerates the types this way and fails
if they differ from the committed ones.

    uv run python -m sms.scripts.dump_openapi > web/.openapi.json

Settings still have to validate (DATABASE_URL etc. must be set), because
importing the app imports them.
"""

import json
import sys

from sms.main import app


def main() -> None:
    # sort_keys keeps the output stable run to run, so a regenerated file
    # only differs when the API actually changed.
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
