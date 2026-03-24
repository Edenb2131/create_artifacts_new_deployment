import json
import os
from dataclasses import dataclass, field
from typing import Optional

from exceptions import ConfigError

# ---------------------------------------------------------------------------
# Try to load credentials from credentials.py (gitignored).
# Fall back to empty strings so env vars / CLI flags can still supply them.
# ---------------------------------------------------------------------------
try:
    from credentials import (
        ARTIFACTORY_URL as _CRED_URL,
        ARTIFACTORY_USERNAME as _CRED_USER,
        ARTIFACTORY_PASSWORD as _CRED_PASS,
    )
except ImportError:
    _CRED_URL = _CRED_USER = _CRED_PASS = ""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ArtifactoryConfig:
    url: str
    username: str
    password: str
    jfrog_cli_name: str = "demo-server"
    request_timeout: int = 30
    repo_settle_sleep: int = 2


@dataclass
class PackageConfig:
    # Docker: image names
    docker: list = field(default_factory=lambda: ["nginx", "httpd", "alpine", "ubuntu", "redis"])
    # NPM: package names
    npm: list = field(default_factory=lambda: ["express", "vue", "react", "lodash", "axios"])
    # PyPI: package specs
    pypi: list = field(default_factory=lambda: ["requests", "flask==3.1.1", "numpy", "pandas", "scikit-learn"])
    # Maven: artifact paths relative to repo root (for jf rt dl)
    maven: list = field(default_factory=lambda: [
        "org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.jar",
        "junit/junit/4.13.2/junit-4.13.2.jar",
    ])
    # Helm: chart tarball names (for jf rt dl)
    helm: list = field(default_factory=lambda: [
        "nginx-15.1.1.tgz",
        "redis-17.11.3.tgz",
    ])
    # Go: module proxy paths (for jf rt dl)
    go: list = field(default_factory=lambda: [
        "github.com/gin-gonic/gin/@v/v1.9.1.zip",
        "github.com/gorilla/mux/@v/v1.8.1.zip",
    ])
    # NuGet: package paths relative to repo root (for jf rt dl)
    nuget: list = field(default_factory=lambda: [
        "Newtonsoft.Json/13.0.3/Newtonsoft.Json.13.0.3.nupkg",
        "log4net/2.0.15/log4net.2.0.15.nupkg",
    ])
    # Generic: filenames to generate, upload, then download as test artifacts
    generic: list = field(default_factory=lambda: [
        "generic-artifact-1.txt",
        "generic-artifact-2.txt",
    ])


@dataclass
class AppConfig:
    artifactory: ArtifactoryConfig
    packages: PackageConfig
    repo_types: list = field(default_factory=lambda: ["docker", "npm", "pypi"])
    dry_run: bool = False
    log_level: str = "INFO"
    log_file: Optional[str] = None
    release_bundles: bool = False
    build_name_prefix: str = ""
    skip_repo_creation: bool = False
    skip_pull: bool = False
    skip_build: bool = False
    skip_cleanup: bool = False


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config(config_path: Optional[str], cli_overrides: dict) -> AppConfig:
    """
    Credential priority (highest → lowest):
      1. CLI flags (--url, --username)
      2. Environment variables (ARTIFACTORY_URL, ARTIFACTORY_USERNAME, ARTIFACTORY_PASSWORD)
      3. JSON config file (--config)
      4. credentials.py (gitignored file at project root)
    """
    file_data: dict = {}
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path) as f:
                file_data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise ConfigError(f"Cannot read config file {config_path}: {e}") from e

    url = (
        cli_overrides.get("url")
        or os.environ.get("ARTIFACTORY_URL")
        or file_data.get("url")
        or _CRED_URL
        or None
    )
    username = (
        cli_overrides.get("username")
        or os.environ.get("ARTIFACTORY_USERNAME")
        or file_data.get("username")
        or _CRED_USER
        or None
    )
    password = (
        os.environ.get("ARTIFACTORY_PASSWORD")
        or file_data.get("password")
        or _CRED_PASS
        or None
    )

    if not url:
        raise ConfigError(
            "Artifactory URL not set. Options:\n"
            "  1. Fill in ARTIFACTORY_URL in credentials.py\n"
            "  2. Set env var ARTIFACTORY_URL\n"
            "  3. Use --url flag"
        )
    if not username:
        raise ConfigError(
            "Username not set. Options:\n"
            "  1. Fill in ARTIFACTORY_USERNAME in credentials.py\n"
            "  2. Set env var ARTIFACTORY_USERNAME\n"
            "  3. Use --username flag"
        )
    if not password:
        raise ConfigError(
            "Password not set. Options:\n"
            "  1. Fill in ARTIFACTORY_PASSWORD in credentials.py\n"
            "  2. Set env var ARTIFACTORY_PASSWORD"
        )

    art_cfg = ArtifactoryConfig(
        url=url.rstrip("/"),
        username=username,
        password=password,
        jfrog_cli_name=file_data.get("jfrog_cli_name", "demo-server"),
        request_timeout=int(file_data.get("request_timeout", 30)),
        repo_settle_sleep=int(file_data.get("repo_settle_sleep", 2)),
    )

    pkg_defaults = PackageConfig()
    pkg_data = file_data.get("packages", {})
    pkg_cfg = PackageConfig(
        docker=pkg_data.get("docker", pkg_defaults.docker),
        npm=pkg_data.get("npm", pkg_defaults.npm),
        pypi=pkg_data.get("pypi", pkg_defaults.pypi),
        maven=pkg_data.get("maven", pkg_defaults.maven),
        helm=pkg_data.get("helm", pkg_defaults.helm),
        go=pkg_data.get("go", pkg_defaults.go),
        nuget=pkg_data.get("nuget", pkg_defaults.nuget),
        generic=pkg_data.get("generic", pkg_defaults.generic),
    )

    return AppConfig(
        artifactory=art_cfg,
        packages=pkg_cfg,
        repo_types=cli_overrides.get("repo_types") or file_data.get("repo_types", ["docker", "npm", "pypi"]),
        dry_run=cli_overrides.get("dry_run", False),
        log_level=cli_overrides.get("log_level", file_data.get("log_level", "INFO")),
        log_file=cli_overrides.get("log_file"),
        release_bundles=cli_overrides.get("release_bundles", False),
        build_name_prefix=cli_overrides.get("build_name_prefix", ""),
        skip_repo_creation=cli_overrides.get("skip_repo_creation", False),
        skip_pull=cli_overrides.get("skip_pull", False),
        skip_build=cli_overrides.get("skip_build", False),
        skip_cleanup=cli_overrides.get("skip_cleanup", False),
    )
