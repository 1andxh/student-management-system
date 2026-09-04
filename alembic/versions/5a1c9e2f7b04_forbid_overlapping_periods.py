"""forbid overlapping periods

Every timetable conflict rule keys on period_id, not on wall-clock time, so
two periods covering the same time made the whole feature bypassable: the
same teacher, room and section could be booked into both without any of the
three checks firing. Expressed as an exclusion constraint rather than a
service check, which would race itself.

Revision ID: 5a1c9e2f7b04
Revises: 47199d373232
Create Date: 2026-09-04

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5a1c9e2f7b04'
down_revision: Union[str, Sequence[str], None] = '47199d373232'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # btree_gist is a standard contrib module, needed because the constraint
    # mixes a range operator (&&) with plain equality semantics in one GiST
    # index. CREATE EXTENSION requires superuser, which the local dev/test
    # role has; a deployment under a restricted role would need this granted
    # out of band.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    # Times are lifted onto an arbitrary fixed date so they can be compared
    # as a range — Postgres has no native "timerange" type. The date is
    # irrelevant and identical for every row; only the time-of-day matters.
    op.execute(
        """
        ALTER TABLE periods ADD CONSTRAINT ex_periods_no_overlap
        EXCLUDE USING gist (
            tsrange(
                '2000-01-01'::date + start_time,
                '2000-01-01'::date + end_time
            ) WITH &&
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE periods DROP CONSTRAINT IF EXISTS ex_periods_no_overlap")
    # btree_gist is deliberately left installed — other things may come to
    # depend on it, and dropping an extension is not this migration's to do.
