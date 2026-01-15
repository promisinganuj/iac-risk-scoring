class ResolutionError(RuntimeError):
    """Raised when a ResourceSpec cannot be resolved deterministically."""


class NotFoundError(ResolutionError):
    pass


class AmbiguousMatchError(ResolutionError):
    def __init__(self, message: str, *, candidates: list[dict] | None = None):
        super().__init__(message)
        self.candidates = candidates or []
