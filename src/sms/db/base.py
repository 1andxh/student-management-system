from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Every domain model inherits from this. Alembic's env.py points its
    autogenerate target metadata at Base.metadata, so a domain's models
    module must be imported somewhere reachable from there for autogenerate
    to see new tables."""
