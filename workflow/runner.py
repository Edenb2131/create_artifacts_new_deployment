import logging
import os
import shutil
import time

from artifactory.client import ArtifactoryClient
from artifactory.jfrog_cli import JFrogCLI
from config import AppConfig
from exceptions import ArtifactError, ArtifactoryError, CommandError, ConfigError, ToolNotFoundError
from repo_definitions import REPO_DEFINITIONS


class WorkflowRunner:
    def __init__(self, config: AppConfig):
        self._config = config
        self._client = ArtifactoryClient(config.artifactory, config.dry_run)
        self._cli = JFrogCLI(config.artifactory, config.dry_run)
        self._log = logging.getLogger("workflow")
        self._build_number = str(int(time.time()))
        url_no_scheme = config.artifactory.url.replace("http://", "").replace("https://", "")
        self._clean_url = url_no_scheme

    def _build_name(self, pkg_type: str) -> str:
        return f"{self._config.build_name_prefix}{pkg_type}"

    # ------------------------------------------------------------------
    # Pre-flight
    # ------------------------------------------------------------------

    def preflight(self) -> None:
        self._log.info("Running pre-flight checks...")
        if not self._client.check_connectivity():
            raise ArtifactoryError(
                f"Cannot reach Artifactory at {self._config.artifactory.url}. Aborting."
            )
        self._log.info("Artifactory connectivity OK")

        self._cli.check_tool("jf")
        selected = self._config.repo_types
        if "docker" in selected:
            self._cli.check_tool("docker")
        if "npm" in selected:
            self._cli.check_tool("npm")
        if "pypi" in selected:
            self._cli.check_tool("pip")
        if "go" in selected:
            self._cli.check_tool("go")
        self._log.info("All required tools found on PATH")

    # ------------------------------------------------------------------
    # Repo creation
    # ------------------------------------------------------------------

    def create_repos(self, types: list) -> None:
        self._log.info("Creating repositories for types: %s", types)
        failures = []
        for pkg_type in types:
            if pkg_type not in REPO_DEFINITIONS:
                self._log.warning("Unknown repo type '%s', skipping.", pkg_type)
                continue
            rd = REPO_DEFINITIONS[pkg_type]
            for repo_name, rclass, extra in [
                (rd.local_name,   "local",   rd.local_extra),
                (rd.remote_name,  "remote",  rd.remote_extra),
                (rd.virtual_name, "virtual", rd.virtual_extra),
            ]:
                payload = self._build_repo_payload(rclass, rd, extra)
                try:
                    self._client.create_repo(repo_name, payload)
                except ArtifactoryError as e:
                    self._log.warning("Non-fatal repo error for %s: %s", repo_name, e)
                    failures.append(repo_name)

        if failures:
            self._log.warning("Repo creation had failures for: %s", failures)

        sleep_sec = self._config.artifactory.repo_settle_sleep
        self._log.debug("Sleeping %ds for repos to settle...", sleep_sec)
        if not self._config.dry_run:
            time.sleep(sleep_sec)

    def _build_repo_payload(self, rclass: str, rd, extra: dict) -> dict:
        if rclass == "local":
            base = {"rclass": "local", "packageType": rd.package_type}
        elif rclass == "remote":
            base = {"rclass": "remote", "url": rd.remote_url, "packageType": rd.package_type}
        elif rclass == "virtual":
            base = {
                "rclass": "virtual",
                "packageType": rd.package_type,
                "repositories": [rd.local_name, rd.remote_name],
                "defaultDeploymentRepo": rd.local_name,
            }
        else:
            raise ValueError(f"Unknown rclass: {rclass}")
        base.update(extra)
        return base

    # ------------------------------------------------------------------
    # CLI configuration
    # ------------------------------------------------------------------

    def configure_cli(self, types: list) -> None:
        self._log.info("Configuring JFrog CLI...")
        self._cli.login()
        if "npm" in types:
            self._cli.setup_npm(REPO_DEFINITIONS["npm"].virtual_name)
        if "pypi" in types:
            self._cli.setup_pypi(REPO_DEFINITIONS["pypi"].virtual_name)
        if "go" in types:
            self._cli.setup_go(REPO_DEFINITIONS["go"].virtual_name)

    # ------------------------------------------------------------------
    # Artifact pulling
    # ------------------------------------------------------------------

    def pull_artifacts(self, types: list) -> None:
        self._log.info("Pulling artifacts...")
        dispatch = {
            "docker":  lambda: self._pull_docker(self._config.packages.docker),
            "npm":     lambda: self._pull_npm(self._config.packages.npm),
            "pypi":    lambda: self._pull_pypi(self._config.packages.pypi),
            "maven":   lambda: self._pull_via_rt_dl("maven", self._config.packages.maven),
            "helm":    lambda: self._pull_via_rt_dl("helm", self._config.packages.helm),
            "go":      lambda: self._pull_via_rt_dl("go", self._config.packages.go),
            "nuget":   lambda: self._pull_via_rt_dl("nuget", self._config.packages.nuget),
            "generic": lambda: self._pull_generic(self._config.packages.generic),
        }
        for t in types:
            if t in dispatch:
                dispatch[t]()

    def _pull_docker(self, images: list) -> None:
        if not images:
            return
        rd = REPO_DEFINITIONS["docker"]
        registry = f"{self._clean_url}/{rd.virtual_name}"
        try:
            self._cli.docker_login(self._clean_url)
        except CommandError as e:
            self._log.error("Docker login failed, skipping all docker pulls: %s", e)
            return
        build_name = self._build_name("docker")
        for image in images:
            try:
                self._cli.docker_pull(f"{registry}/{image}", build_name, self._build_number)
            except CommandError as e:
                self._log.error("Failed to pull docker image %s: %s", image, e)

    def _pull_npm(self, packages: list) -> None:
        if not packages:
            return
        build_name = self._build_name("npm")
        for pkg in packages:
            try:
                self._cli.add_npm_dependency(pkg)
                self._cli.npm_install(pkg, build_name, self._build_number)
            except (CommandError, ArtifactError) as e:
                self._log.error("Failed to install npm package %s: %s", pkg, e)

    def _pull_pypi(self, packages: list) -> None:
        if not packages:
            return
        build_name = self._build_name("pypi")
        for pkg in packages:
            try:
                self._cli.pip_install(pkg, self._clean_url, build_name, self._build_number)
            except CommandError as e:
                self._log.error("Failed to install pip package %s: %s", pkg, e)

    def _pull_via_rt_dl(self, pkg_type: str, artifact_paths: list) -> None:
        """Download artifacts from a virtual repo using 'jf rt dl'. Used for maven/helm/go/nuget."""
        if not artifact_paths:
            return
        rd = REPO_DEFINITIONS[pkg_type]
        build_name = self._build_name(pkg_type)
        for path in artifact_paths:
            try:
                self._cli.rt_download(f"{rd.virtual_name}/{path}", build_name, self._build_number)
            except CommandError as e:
                self._log.error("Failed to download %s artifact %s: %s", pkg_type, path, e)

    def _pull_generic(self, filenames: list) -> None:
        """Upload generated test files to generic-local, then download via generic-virtual."""
        if not filenames:
            return
        rd = REPO_DEFINITIONS["generic"]
        build_name = self._build_name("generic")
        for filename in filenames:
            try:
                if not self._config.dry_run:
                    with open(filename, "w") as f:
                        f.write(f"generic test artifact: {filename}\nbuild: {self._build_number}\n")
                self._cli.rt_upload(filename, f"{rd.local_name}/{filename}", build_name, self._build_number)
                self._cli.rt_download(f"{rd.virtual_name}/{filename}", build_name, self._build_number)
            except (CommandError, OSError) as e:
                self._log.error("Failed to process generic artifact %s: %s", filename, e)
            finally:
                if not self._config.dry_run:
                    try:
                        if os.path.isfile(filename):
                            os.remove(filename)
                    except OSError:
                        pass

    # ------------------------------------------------------------------
    # Build publishing
    # ------------------------------------------------------------------

    def create_builds(self, types: list) -> None:
        self._log.info("Publishing builds...")
        for pkg_type in types:
            build_name = self._build_name(pkg_type)
            try:
                self._cli.collect_env(build_name, self._build_number)
                if pkg_type == "npm":
                    self._cli.npm_publish(build_name, self._build_number)
                self._cli.publish_build(build_name, self._build_number)
            except CommandError as e:
                self._log.error("Build publish failed for %s: %s", pkg_type, e)

    # ------------------------------------------------------------------
    # Release bundles
    # ------------------------------------------------------------------

    def create_release_bundles(self, types: list) -> None:
        self._log.info("Creating release bundles...")
        for pkg_type in types:
            if pkg_type not in REPO_DEFINITIONS:
                continue
            rd = REPO_DEFINITIONS[pkg_type]
            try:
                self._client.create_release_bundle(
                    f"{pkg_type}-bundle", self._build_number, rd.local_name
                )
            except ArtifactoryError as e:
                self._log.error("Failed to create release bundle for %s: %s", pkg_type, e)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        if self._config.skip_cleanup:
            self._log.info("Skipping cleanup (--skip-cleanup).")
            return
        if self._config.dry_run:
            self._log.info("DRY RUN: would clean up temp files and JFrog CLI config.")
            return
        self._log.info("Cleaning up...")
        self._cli.logout()
        for path in ["node_modules", "__pycache__", ".jfrog"]:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                    self._log.debug("Removed directory: %s", path)
            except OSError as e:
                self._log.warning("Could not remove %s: %s", path, e)
        for path in ["package-lock.json", "package.json", ".npmrc"]:
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    self._log.debug("Removed file: %s", path)
            except OSError as e:
                self._log.warning("Could not remove %s: %s", path, e)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> int:
        if self._config.dry_run:
            self._log.info("DRY RUN mode active — no changes will be made.")

        self._log.info("Build number: %s", self._build_number)
        selected = self._config.repo_types

        try:
            self.preflight()

            if not self._config.skip_repo_creation:
                self.create_repos(selected)

            self.configure_cli(selected)

            if not self._config.skip_pull:
                self.pull_artifacts(selected)

            if not self._config.skip_build:
                self.create_builds(selected)

            if self._config.release_bundles:
                self.create_release_bundles(selected)

        except (ConfigError, ArtifactoryError, ToolNotFoundError) as e:
            self._log.error("Fatal error: %s", e)
            self.cleanup()
            return 1
        except KeyboardInterrupt:
            self._log.warning("Interrupted by user.")
            self.cleanup()
            return 1

        self.cleanup()
        self._log.info("All done!")
        return 0
