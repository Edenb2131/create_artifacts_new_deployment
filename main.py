"""
Artifactory demo environment setup.

Quickstart:
  1. cp credentials.example.py credentials.py
  2. Fill in your credentials in credentials.py
  3. pip install -r requirements.txt
  4. python main.py

All available repo types: docker, npm, pypi, maven, helm, go, nuget, generic
"""

import argparse
import logging
import sys

from config import load_config
from exceptions import ConfigError
from repo_definitions import REPO_DEFINITIONS
from workflow.runner import WorkflowRunner


def setup_logging(level: str = "INFO", log_file: str = None) -> None:
    fmt = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    handlers = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=handlers,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    all_types = list(REPO_DEFINITIONS.keys())
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Automate JFrog Artifactory demo environment setup.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"Available repo types: {', '.join(all_types)}\n\n"
            "Credential priority (highest → lowest):\n"
            "  1. --url / --username flags\n"
            "  2. Env vars: ARTIFACTORY_URL, ARTIFACTORY_USERNAME, ARTIFACTORY_PASSWORD\n"
            "  3. --config JSON file\n"
            "  4. credentials.py  (copy credentials.example.py → credentials.py and fill it in)"
        ),
    )

    # Connection
    parser.add_argument("--url", help="Artifactory base URL (overrides credentials.py / env var)")
    parser.add_argument("--username", help="Artifactory username (overrides credentials.py / env var)")

    # Config file
    parser.add_argument("--config", metavar="PATH", help="Path to optional JSON config file")

    # Repo type selection
    parser.add_argument(
        "--repo-types", nargs="+", choices=all_types, default=None, metavar="TYPE",
        help=f"Repo types to create/use. Default: docker npm pypi. Choices: {all_types}",
    )

    # Phase control
    parser.add_argument("--skip-repo-creation", action="store_true", help="Skip repo creation")
    parser.add_argument("--skip-pull",           action="store_true", help="Skip artifact pulling")
    parser.add_argument("--skip-build",          action="store_true", help="Skip build publishing")
    parser.add_argument("--skip-cleanup",        action="store_true", help="Skip cleanup")
    parser.add_argument("--release-bundles",     action="store_true", help="Create release bundles")

    # Behavior
    parser.add_argument("--dry-run", "-n",  action="store_true", help="Preview actions without executing")
    parser.add_argument("--verbose", "-v",  action="store_true", help="Enable DEBUG logging")
    parser.add_argument("--log-file",       metavar="PATH",       help="Also write logs to this file")
    parser.add_argument("--build-name-prefix", default="", metavar="PREFIX",
                        help="Prefix for build names (e.g. 'demo-' → 'demo-docker')")

    return parser


if __name__ == "__main__":
    parser = build_arg_parser()
    args = parser.parse_args()

    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level, log_file=args.log_file)

    cli_overrides = {
        "url":                args.url,
        "username":           args.username,
        "repo_types":         args.repo_types,
        "dry_run":            args.dry_run,
        "log_level":          log_level,
        "log_file":           args.log_file,
        "release_bundles":    args.release_bundles,
        "build_name_prefix":  args.build_name_prefix,
        "skip_repo_creation": args.skip_repo_creation,
        "skip_pull":          args.skip_pull,
        "skip_build":         args.skip_build,
        "skip_cleanup":       args.skip_cleanup,
    }

    try:
        config = load_config(args.config, cli_overrides)
    except ConfigError as e:
        logging.getLogger("main").error("Configuration error: %s", e)
        sys.exit(1)

    runner = WorkflowRunner(config)
    sys.exit(runner.run())
