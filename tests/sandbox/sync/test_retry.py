def test_retry_on_failure():
    from sandbox.sync.retry import retry_with_backoff

    call_count = 0

    @retry_with_backoff(max_retries=3, backoff_factor=0.1)
    def failing_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Temporary failure")
        return "success"

    result = failing_func()
    assert result == "success"
    assert call_count == 3
