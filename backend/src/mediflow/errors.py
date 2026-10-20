"""Safe consistent API errors; do not return request bodies or raw provider errors."""

from mediflow.contracts import ErrorCode


class ApplicationError(Exception):
    def __init__(self, code: ErrorCode, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.safe_message = message
