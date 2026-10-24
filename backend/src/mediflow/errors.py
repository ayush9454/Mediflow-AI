"""Safe consistent API errors; do not return request bodies or raw provider errors."""

from mediflow.contracts import ErrorCode


class ProcessingFailure(Exception):
    """Shared across CLI entrypoints and provider/worker process boundaries."""

    def __init__(self, code: ErrorCode, *, transient: bool = False):
        super().__init__(code.value)
        self.code = code
        self.transient = transient


class ApplicationError(Exception):
    def __init__(self, code: ErrorCode, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.safe_message = message
