"""
etl_audit.py — Logs pipeline runs to the etl_runs table.

Called by the GitHub Actions workflow, not by run_pipeline.py.
"""

import os
import sys
from sqlalchemy import create_engine, text


DB_URL = os.getenv("DATABASE_URL", "").strip()


def _get_conn():
    engine = create_engine(DB_URL, pool_pre_ping=True)
    return engine


def start():
    """Insert a 'running' row. Prints the run_id for later steps."""
    engine = _get_conn()
    with engine.begin() as conn:
        run_id = conn.execute(text(
            "INSERT INTO etl_runs (status) VALUES ('running') RETURNING run_id"
        )).scalar()
    print(run_id)


def success(run_id):
    """Mark run as successful."""
    engine = _get_conn()
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE etl_runs
            SET status = 'success', completed_at = NOW(),
                duration_secs = EXTRACT(EPOCH FROM (NOW() - started_at))
            WHERE run_id = :rid
        """), {"rid": int(run_id)})


def fail(run_id, message):
    """Mark run as failed."""
    engine = _get_conn()
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE etl_runs
            SET status = 'failed', completed_at = NOW(),
                duration_secs = EXTRACT(EPOCH FROM (NOW() - started_at)),
                error_message = :msg
            WHERE run_id = :rid
        """), {"rid": int(run_id), "msg": message[:500]})


if __name__ == "__main__":
    action = sys.argv[1]

    if action == "start":
        start()

    elif action == "success":
        success(sys.argv[2])

    elif action == "fail":
        success_id = sys.argv[2]
        msg = sys.argv[3] if len(sys.argv) > 3 else "Unknown error"
        fail(success_id, msg)