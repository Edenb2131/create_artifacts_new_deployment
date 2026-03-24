from typing import Optional


class ArtifactError(Exception):
    """Base exception for this project."""


class ConfigError(ArtifactError):
    """Bad or missing configuration."""


class ArtifactoryError(ArtifactError):
    """HTTP-level failure from Artifactory API."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class ToolNotFoundError(ArtifactError):
    """Required CLI tool not found on PATH."""


class CommandError(ArtifactError):
    """Subprocess command failed."""

    def __init__(self, message: str, returncode: int, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr
