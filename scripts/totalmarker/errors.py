class TotalMarkerError(Exception):
    """A message safe to show without transport/configuration secrets."""


class ConfigError(TotalMarkerError):
    pass


class StorageError(TotalMarkerError):
    pass


class DownloadError(TotalMarkerError):
    pass


class ImageError(TotalMarkerError):
    pass


class FeedError(TotalMarkerError):
    pass
