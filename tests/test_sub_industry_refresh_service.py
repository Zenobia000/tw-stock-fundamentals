from app.sub_industry_refresh_service import SubIndustryRefreshJob


def test_status_is_idle_before_first_start():
    job = SubIndustryRefreshJob()
    assert job.status() == {"status": "idle"}


def test_run_records_per_step_results_without_aborting_on_failure(monkeypatch):
    job = SubIndustryRefreshJob()
    calls = []

    def _ok(argv):
        calls.append("industry_chain")
        return 0

    def _boom(argv):
        calls.append("stock_universe")
        raise RuntimeError("FinMind 額度用完")

    def _ok2(argv):
        calls.append("top100_prices")
        return 0

    monkeypatch.setattr(
        "app.sub_industry_refresh_service._STEPS",
        (
            ("產業標籤", _ok),
            ("前100大名單", _boom),
            ("前100大股價", _ok2),
        ),
    )

    job._state = {"status": "running", "started_at": "t0"}
    job._run()

    # 第二步失敗不擋住第三步照跑
    assert calls == ["industry_chain", "stock_universe", "top100_prices"]

    status = job.status()
    assert status["status"] == "failed"
    assert status["steps"][0] == {"step": "產業標籤", "status": "ok", "error": None}
    assert status["steps"][1]["status"] == "failed"
    assert "FinMind 額度用完" in status["steps"][1]["error"]
    assert status["steps"][2]["status"] == "ok"
    assert "1/3" in status["message"]


def test_run_marks_completed_when_all_steps_succeed(monkeypatch):
    job = SubIndustryRefreshJob()
    monkeypatch.setattr(
        "app.sub_industry_refresh_service._STEPS",
        (("步驟一", lambda argv: 0),),
    )
    job._state = {"status": "running", "started_at": "t0"}
    job._run()
    status = job.status()
    assert status["status"] == "completed"
    assert status["message"] == "回補完成"


def test_start_returns_existing_snapshot_when_already_running():
    job = SubIndustryRefreshJob()
    job._state = {"status": "running", "started_at": "t0", "steps": []}
    result = job.start()
    assert result == {"status": "running", "started_at": "t0", "steps": []}
