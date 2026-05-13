from backend.monitor.infrastructure.web import gateway as monitor_gateway


def test_monitor_gateway_starts_batches_with_explicit_execution_target(monkeypatch):
    captured = {}

    def _start_monitor_evaluation_batch(*, batch_id, execution_base_url, token, scheduler):
        captured.update(
            batch_id=batch_id,
            execution_base_url=execution_base_url,
            token=token,
            scheduler=scheduler,
        )
        return {"accepted": True}

    monkeypatch.setattr(
        monitor_gateway.monitor_evaluation,
        "start_monitor_evaluation_batch",
        _start_monitor_evaluation_batch,
    )

    payload = monitor_gateway.start_evaluation_batch(
        batch_id="batch-1",
        execution_base_url="http://backend-main",
        token="token-1",
        schedule_task=lambda *args, **kwargs: None,
    )

    assert payload == {"accepted": True}
    assert captured["batch_id"] == "batch-1"
    assert captured["execution_base_url"] == "http://backend-main"
    assert captured["token"] == "token-1"
