class InputValidationError(Exception):
    """Tool parameter validation failed."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        details: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = [] if details is None else details
