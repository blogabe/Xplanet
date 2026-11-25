class TotalMarkerError(Exception):
    """A message safe to show without transport/configuration secrets."""


class ConfigError(TotalMarkerError):
    pass


class StorageError(TotalMarkerError):
    pass


class DownloadError(TotalMarkerError):
    pass


class SourceStatusError(DownloadError):
    """Non-success HTTP status with the bounded diagnostic text."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class ImageError(TotalMarkerError):
    pass


class FeedError(TotalMarkerError):
    pass
