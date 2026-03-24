import json
import logging
import os
import subprocess
import time

from config import ArtifactoryConfig
from exceptions import ArtifactError, CommandError, ToolNotFoundError


PACKAGE_JSON_PATH = "package.json"
BASE_PACKAGE_JSON = {
    "name": "create-artifacts-new-deployment",
    "version": "1.0.0",
    "dependencies": {},
}


class JFrogCLI:
    def __init__(self, config: ArtifactoryConfig, dry_run: bool = False):
        self._config = config
        self._dry_run = dry_run
        self._log = logging.getLogger("jfrog.cli")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _redact(self, cmd: list) -> list:
        return ["***" if token == self._config.password else token for token in cmd]

    def _run(self, cmd: list, description: str, *, check: bool = True,
             retries: int = 1) -> subprocess.CompletedProcess:
        redacted = " ".join(self._redact(cmd))
        self._log.debug("Running [%s]: %s", description, redacted)
        if self._dry_run:
            self._log.info("DRY RUN: would run: %s", redacted)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        last_exc = None
        for attempt in range(max(retries, 1)):
            try:
                result = subprocess.run(cmd, check=check, capture_output=True, text=True)
                if result.stdout:
                    self._log.debug("stdout: %s", result.stdout.strip())
                return result
            except subprocess.CalledProcessError as e:
                last_exc = e
                stderr_msg = e.stderr.strip() if e.stderr else ""
                if attempt < retries - 1:
                    wait = 2 ** attempt
                    self._log.warning(
                        "Command failed (attempt %d/%d): %s. Retrying in %ds...",
                        attempt + 1, retries, redacted, wait,
                    )
                    time.sleep(wait)
                else:
                    self._log.error("Command failed: %s", redacted)
                    if stderr_msg:
                        self._log.error("stderr: %s", stderr_msg)
                    raise CommandError(
                        f"{description} failed (exit {e.returncode})",
                        returncode=e.returncode,
                        stderr=stderr_msg,
                    ) from e
        raise last_exc

    # ------------------------------------------------------------------
    # Pre-flight
    # ------------------------------------------------------------------

    def check_tool(self, tool: str) -> None:
        try:
            subprocess.run(["which", tool], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            raise ToolNotFoundError(
                f"Required tool '{tool}' not found on PATH. Please install it before running."
            )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self) -> None:
        cfg = self._config
        self._run(
            ["jf", "c", "add", "--interactive=false",
             "--url", cfg.url,
             "--user", cfg.username,
             "--password", cfg.password,
             cfg.jfrog_cli_name],
            "JFrog CLI login",
        )
        self._run(["jf", "c", "use", cfg.jfrog_cli_name], "Set JFrog CLI context")

    def logout(self) -> None:
        try:
            self._run(
                ["jf", "c", "remove", self._config.jfrog_cli_name, "--quiet"],
                "JFrog CLI logout",
            )
        except (CommandError, Exception) as e:
            self._log.warning("Logout failed (non-critical): %s", e)

    # ------------------------------------------------------------------
    # Package type setup
    # ------------------------------------------------------------------

    def setup_npm(self, virtual_repo: str) -> None:
        cfg = self._config
        self._run(
            ["jf", "npmc",
             "--server-id-resolve", cfg.jfrog_cli_name,
             "--server-id-deploy", cfg.jfrog_cli_name,
             "--repo-resolve", virtual_repo,
             "--repo-deploy", virtual_repo],
            "Setup NPM resolver/deployer",
        )

    def setup_pypi(self, virtual_repo: str) -> None:
        cfg = self._config
        self._run(
            ["jf", "pipc",
             "--server-id-resolve", cfg.jfrog_cli_name,
             "--server-id-deploy", cfg.jfrog_cli_name,
             "--repo-resolve", virtual_repo,
             "--repo-deploy", virtual_repo],
            "Setup PyPI resolver/deployer",
        )

    def setup_go(self, virtual_repo: str) -> None:
        cfg = self._config
        self._run(
            ["jf", "go-config",
             "--server-id-resolve", cfg.jfrog_cli_name,
             "--repo-resolve", virtual_repo],
            "Setup Go resolver",
        )

    # ------------------------------------------------------------------
    # Docker
    # ------------------------------------------------------------------

    def docker_login(self, registry: str) -> None:
        cfg = self._config
        self._run(
            ["docker", "login", registry, "-u", cfg.username, "-p", cfg.password],
            f"Docker login to {registry}",
        )

    def docker_pull(self, image_ref: str, build_name: str, build_number: str) -> None:
        self._run(
            ["jf", "docker", "pull", image_ref,
             "--build-name", build_name, "--build-number", build_number],
            f"Docker pull {image_ref}",
            retries=2,
        )

    # ------------------------------------------------------------------
    # NPM
    # ------------------------------------------------------------------

    def npm_install(self, pkg: str, build_name: str, build_number: str) -> None:
        self._run(
            ["jf", "npm", "install", pkg,
             "--build-name", build_name, "--build-number", build_number],
            f"npm install {pkg}",
        )

    def npm_publish(self, build_name: str, build_number: str) -> None:
        self._run(
            ["jf", "npm", "publish",
             "--build-name", build_name, "--build-number", build_number],
            "npm publish",
        )

    def ensure_package_json(self) -> dict:
        if not os.path.exists(PACKAGE_JSON_PATH):
            if not self._dry_run:
                try:
                    with open(PACKAGE_JSON_PATH, "w") as f:
                        json.dump(BASE_PACKAGE_JSON, f, indent=2)
                except OSError as e:
                    raise ArtifactError(f"Cannot write package.json: {e}") from e
            return dict(BASE_PACKAGE_JSON)
        try:
            with open(PACKAGE_JSON_PATH) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise ArtifactError(f"Cannot read package.json: {e}") from e

    def save_package_json(self, data: dict) -> None:
        if self._dry_run:
            self._log.debug("DRY RUN: would write package.json")
            return
        try:
            with open(PACKAGE_JSON_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            raise ArtifactError(f"Cannot write package.json: {e}") from e

    def add_npm_dependency(self, pkg_name: str) -> None:
        data = self.ensure_package_json()
        data.setdefault("dependencies", {})
        if pkg_name not in data["dependencies"]:
            data["dependencies"][pkg_name] = "*"
        self.save_package_json(data)

    # ------------------------------------------------------------------
    # PyPI
    # ------------------------------------------------------------------

    def pip_install(self, pkg: str, clean_url: str, build_name: str, build_number: str) -> None:
        self._run(
            ["jf", "pip", "install", pkg,
             "--trusted-host", clean_url,
             "--build-name", build_name,
             "--build-number", build_number,
             "--no-cache-dir", "--force-reinstall"],
            f"pip install {pkg}",
        )

    # ------------------------------------------------------------------
    # Generic Artifactory CLI (rt dl / rt upload)
    # ------------------------------------------------------------------

    def rt_download(self, artifact_path: str, build_name: str, build_number: str) -> None:
        self._run(
            ["jf", "rt", "dl", artifact_path,
             "--build-name", build_name, "--build-number", build_number],
            f"Download {artifact_path}",
            retries=2,
        )

    def rt_upload(self, local_path: str, target: str, build_name: str, build_number: str) -> None:
        self._run(
            ["jf", "rt", "upload", local_path, target,
             "--build-name", build_name, "--build-number", build_number],
            f"Upload {local_path} -> {target}",
        )

    # ------------------------------------------------------------------
    # Build info
    # ------------------------------------------------------------------

    def collect_env(self, build_name: str, build_number: str) -> None:
        self._run(["jf", "rt", "bce", build_name, build_number], "Collect env vars")

    def publish_build(self, build_name: str, build_number: str) -> None:
        self._run(["jf", "rt", "bp", build_name, build_number], f"Publish build {build_name}")
