import logging
import time
from typing import Optional

import requests

from config import ArtifactoryConfig
from exceptions import ArtifactoryError


def _with_retries(fn, *, retries: int = 3, backoff_base: float = 1.0,
                  backoff_factor: float = 2.0,
                  retriable_exceptions=(requests.ConnectionError, requests.Timeout),
                  logger: logging.Logger):
    last_exc = None
    for attempt in range(retries):
        try:
            return fn()
        except retriable_exceptions as e:
            last_exc = e
            wait = backoff_base * (backoff_factor ** attempt)
            logger.warning("Attempt %d/%d failed (%s). Retrying in %.1fs...", attempt + 1, retries, e, wait)
            time.sleep(wait)
    raise last_exc


class ArtifactoryClient:
    def __init__(self, config: ArtifactoryConfig, dry_run: bool = False):
        self._config = config
        self._dry_run = dry_run
        self._session = requests.Session()
        self._session.auth = (config.username, config.password)
        self._session.headers.update({"Content-Type": "application/json"})
        self._log = logging.getLogger("artifactory.client")

    def check_connectivity(self) -> bool:
        url = f"{self._config.url}/artifactory/api/system/ping"
        self._log.debug("Connectivity check: GET %s", url)
        if self._dry_run:
            self._log.info("DRY RUN: would GET %s", url)
            return True
        try:
            resp = self._session.get(url, timeout=self._config.request_timeout)
            if resp.status_code == 401:
                raise ArtifactoryError(
                    "Artifactory returned 401 Unauthorized — check your username and password in credentials.py",
                    status_code=401,
                )
            return True  # any other HTTP response means the server is up
        except requests.RequestException as e:
            self._log.error("Connectivity check failed: %s", e)
            return False

    def create_repo(self, repo_name: str, payload: dict) -> str:
        """Returns 'created', 'exists', or raises ArtifactoryError."""
        url = f"{self._config.url}/artifactory/api/repositories/{repo_name}"
        self._log.debug("Creating repo %s", repo_name)
        if self._dry_run:
            self._log.info("DRY RUN: would PUT %s (rclass=%s)", url, payload.get("rclass"))
            return "created"

        def do_put():
            return self._session.put(url, json=payload, timeout=self._config.request_timeout)

        try:
            resp = _with_retries(do_put, logger=self._log)
        except (requests.ConnectionError, requests.Timeout) as e:
            raise ArtifactoryError(f"Network error creating repo {repo_name}: {e}") from e

        if resp.status_code in (200, 201):
            self._log.info("Created repo: %s", repo_name)
            return "created"
        if resp.status_code == 400 and "already exists" in resp.text:
            self._log.info("Repo already exists: %s", repo_name)
            return "exists"
        raise ArtifactoryError(
            f"Failed to create repo {repo_name} (HTTP {resp.status_code}): {resp.text}",
            status_code=resp.status_code,
        )

    def create_release_bundle(self, name: str, version: str, repo_name: str) -> None:
        url = f"{self._config.url}/lifecycle/api/v2/release_bundle"
        payload = {
            "release_bundle_name": name,
            "release_bundle_version": version,
            "source_type": "aql",
            "source": {
                "aql": f'items.find({{"repo":"{repo_name}"}})'
            },
        }
        self._log.debug("Creating release bundle %s:%s", name, version)
        if self._dry_run:
            self._log.info("DRY RUN: would POST release bundle %s:%s", name, version)
            return

        try:
            resp = self._session.post(url, json=payload, timeout=self._config.request_timeout)
        except requests.RequestException as e:
            raise ArtifactoryError(f"Network error creating release bundle {name}: {e}") from e

        if resp.status_code in (200, 201):
            self._log.info("Created release bundle: %s:%s", name, version)
        else:
            raise ArtifactoryError(
                f"Failed to create release bundle {name} (HTTP {resp.status_code}): {resp.text}",
                status_code=resp.status_code,
            )
