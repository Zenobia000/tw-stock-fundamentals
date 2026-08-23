from datetime import UTC, datetime, timedelta

from app.refresh_service import RefreshJobs


def test_purge_stale_removes_old_finished_jobs_but_keeps_recent_and_running():
    jobs = RefreshJobs()
    old_finished_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
    recent_finished_at = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    jobs._jobs = {
        "2330": {"code": "2330", "status": "completed", "finished_at": old_finished_at},
        "2317": {"code": "2317", "status": "completed", "finished_at": recent_finished_at},
        "0050": {"code": "0050", "status": "running", "finished_at": None},
    }

    jobs._purge_stale()

    assert set(jobs._jobs) == {"2317", "0050"}


def test_start_purges_stale_jobs_before_scheduling_new_one(monkeypatch):
    jobs = RefreshJobs()
    old_finished_at = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
    jobs._jobs = {
        "2330": {"code": "2330", "status": "completed", "finished_at": old_finished_at},
    }
    monkeypatch.setattr(jobs._executor, "submit", lambda *_args, **_kwargs: None)

    jobs.start("2317")

    assert "2330" not in jobs._jobs
    assert jobs._jobs["2317"]["status"] == "running"
