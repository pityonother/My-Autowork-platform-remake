from __future__ import annotations


class DistributionError(RuntimeError):
    def __init__(self, user_message: str, *, technical_detail: str = "") -> None:
        super().__init__(technical_detail or user_message)
        self.user_message = user_message
        self.technical_detail = technical_detail


class ManifestError(DistributionError):
    pass


class DownloadError(DistributionError):
    pass


class HashMismatchError(DownloadError):
    pass


class InstallError(DistributionError):
    pass


class ModuleRunningError(InstallError):
    pass


class LaunchError(DistributionError):
    pass
