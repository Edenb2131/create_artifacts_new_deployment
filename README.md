# create_artifacts_new_deployment

Automates the setup of a JFrog Artifactory demo environment — creating repositories, pulling artifacts through Artifactory, publishing build info, and optionally generating release bundles. Supports 8 package types and uses the JFrog CLI for every operation.

---

## Table of Contents

- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Credentials Setup](#credentials-setup)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Supported Repository Types](#supported-repository-types)
- [CLI Reference](#cli-reference)
- [Usage Examples](#usage-examples)
- [JSON Config File](#json-config-file)
- [Dry-Run Mode](#dry-run-mode)
- [Troubleshooting](#troubleshooting)

---

## Project Structure

```
create_artifacts_new_deployment/
├── main.py                   # Entry point — CLI parsing and startup
├── config.py                 # Configuration dataclasses and loader
├── exceptions.py             # Custom exception types
├── repo_definitions.py       # Repository definitions for all 8 package types
├── artifactory/
│   ├── client.py             # ArtifactoryClient — REST API calls
│   └── jfrog_cli.py          # JFrogCLI — wraps the jf CLI tool
├── workflow/
│   └── runner.py             # WorkflowRunner — orchestrates the full workflow
├── credentials.example.py    # Template for credentials (committed, safe to share)
├── credentials.py            # Your actual credentials (gitignored, never uploaded)
├── requirements.txt          # Python dependencies
└── README.md
```

---

## Prerequisites

### Required

| Tool | Purpose | Install |
|------|---------|---------|
| Python 3.10+ | Run the script | [python.org](https://python.org) |
| JFrog CLI (`jf`) | All Artifactory operations | [jfrog.com/getcli](https://jfrog.com/getcli/) |
| A running JFrog Artifactory instance | Target platform | — |

### Required per repo type

| Repo type | Additional tool needed |
|-----------|----------------------|
| `docker` | Docker Desktop / Docker CLI |
| `npm` | Node.js + npm |
| `pypi` | pip |
| `go` | Go toolchain |
| `maven`, `helm`, `nuget`, `generic` | None — uses `jf rt dl` directly |

Only install what you need for the types you plan to use.

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Edenb2131/create_artifacts_new_deployment.git
cd create_artifacts_new_deployment

# 2. Install the Python dependency
pip install -r requirements.txt
```

---

## Credentials Setup

Credentials are **never hardcoded** and `credentials.py` is gitignored so it will never be uploaded to GitHub.

### Step 1 — Copy the example file

```bash
cp credentials.example.py credentials.py
```

### Step 2 — Fill in your values

Open `credentials.py` and set your Artifactory details:

```python
ARTIFACTORY_URL      = "http://172.16.1.128:8082"
ARTIFACTORY_USERNAME = "admin"
ARTIFACTORY_PASSWORD = "Password1!"
```

That's it — the script will automatically load these values on every run.

---

### Alternative: Environment Variables

If you prefer not to write credentials to a file at all, export them as environment variables instead. These take priority over `credentials.py`.

```bash
export ARTIFACTORY_URL="http://172.16.1.128:8082"
export ARTIFACTORY_USERNAME="admin"
export ARTIFACTORY_PASSWORD="Password1!"
```

---

### Alternative: CLI Flags

URL and username can also be passed as flags (password must still come from `credentials.py` or the env var):

```bash
python main.py --url http://172.16.1.128:8082 --username admin
```

---

### Credential Priority

When multiple sources are set, the highest-priority source wins:

| Priority | Source |
|----------|--------|
| 1 (highest) | `--url` / `--username` CLI flags |
| 2 | `ARTIFACTORY_URL` / `ARTIFACTORY_USERNAME` / `ARTIFACTORY_PASSWORD` env vars |
| 3 | `--config` JSON file |
| 4 (lowest) | `credentials.py` |

---

## Quick Start

Once credentials are set:

```bash
# Run with defaults — creates docker, npm, pypi repos and pulls artifacts
python main.py

# Preview everything without making any changes
python main.py --dry-run --verbose

# Set up all 8 repo types
python main.py --repo-types docker npm pypi maven helm go nuget generic
```

---

## How It Works

Each run executes the following phases in order:

```
1. Pre-flight checks
   ├── Verify Artifactory is reachable
   └── Verify required CLI tools are on PATH

2. Create repositories
   └── For each selected type: create local + remote + virtual repos

3. Configure JFrog CLI
   ├── jf c add  (log in)
   └── Set up resolvers for npm / pypi / go

4. Pull artifacts
   └── Download packages through Artifactory (cached in remote repos)

5. Publish build info
   └── jf rt bce + jf rt bp for each type

6. Create release bundles  (optional, --release-bundles)

7. Cleanup
   └── Remove temp files and JFrog CLI config
```

Each phase can be skipped individually — see [CLI Reference](#cli-reference).

---

## Supported Repository Types

For each type, the script creates three Artifactory repositories:

| Repo | Purpose |
|------|---------|
| `<type>-local` | Stores artifacts you deploy internally |
| `<type>-remote` | Proxies and caches an external registry |
| `<type>-virtual` | Unified view combining local + remote |

All artifact pulls go through the **virtual** repo.

---

### docker
- **Remote upstream:** `https://registry-1.docker.io`
- **Pull method:** `jf docker pull`
- **Default artifacts:** nginx, httpd, alpine, ubuntu, redis

### npm
- **Remote upstream:** `https://registry.npmjs.org`
- **Pull method:** `jf npm install`
- **Default packages:** express, vue, react, lodash, axios

### pypi
- **Remote upstream:** `https://files.pythonhosted.org`
- **Pull method:** `jf pip install`
- **Default packages:** requests, flask==3.1.1, numpy, pandas, scikit-learn

### maven
- **Remote upstream:** `https://repo1.maven.org/maven2`
- **Pull method:** `jf rt dl` (downloads artifact JARs directly)
- **Default artifacts:**
  - `org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.jar`
  - `junit/junit/4.13.2/junit-4.13.2.jar`

### helm
- **Remote upstream:** `https://charts.bitnami.com/bitnami`
- **Pull method:** `jf rt dl` (downloads chart `.tgz` files)
- **Default charts:** nginx-15.1.1.tgz, redis-17.11.3.tgz

### go
- **Remote upstream:** `https://goproxy.io`
- **Pull method:** `jf rt dl` (downloads module zip files via Go proxy path format)
- **Default modules:**
  - `github.com/gin-gonic/gin/@v/v1.9.1.zip`
  - `github.com/gorilla/mux/@v/v1.8.1.zip`

### nuget
- **Remote upstream:** `https://www.nuget.org`
- **Pull method:** `jf rt dl` (downloads `.nupkg` files)
- **Default packages:**
  - `Newtonsoft.Json/13.0.3/Newtonsoft.Json.13.0.3.nupkg`
  - `log4net/2.0.15/log4net.2.0.15.nupkg`

### generic
- **Remote upstream:** `https://releases.hashicorp.com`
- **Pull method:** Generate a test file → `jf rt upload` to local → `jf rt dl` from virtual
- **Default artifacts:** generic-artifact-1.txt, generic-artifact-2.txt

---

## CLI Reference

```
python main.py [options]
```

### Connection

| Flag | Description |
|------|-------------|
| `--url URL` | Artifactory base URL (overrides credentials.py / env var) |
| `--username USER` | Artifactory username (overrides credentials.py / env var) |
| `--config PATH` | Path to an optional JSON config file |

### Repository Types

| Flag | Description |
|------|-------------|
| `--repo-types TYPE [TYPE ...]` | Which types to set up. Default: `docker npm pypi`. Choices: `docker npm pypi maven helm go nuget generic` |

### Phase Control

| Flag | Description |
|------|-------------|
| `--skip-repo-creation` | Skip creating repositories (useful when repos already exist) |
| `--skip-pull` | Skip pulling artifacts |
| `--skip-build` | Skip publishing build info |
| `--release-bundles` | Create a release bundle per type after build publish |
| `--skip-cleanup` | Do not delete temp files or remove JFrog CLI config |

### Behavior

| Flag | Description |
|------|-------------|
| `--dry-run` / `-n` | Print all actions without executing anything |
| `--verbose` / `-v` | Show DEBUG-level logs (every CLI command, HTTP request, etc.) |
| `--log-file PATH` | Write logs to a file in addition to the terminal |
| `--build-name-prefix PREFIX` | Prefix added to all build names (e.g. `demo-` → `demo-docker`) |

---

## Usage Examples

### Basic run (docker, npm, pypi — the defaults)

```bash
python main.py
```

---

### Preview all actions without executing anything

```bash
python main.py --dry-run --verbose
```

Expected output:
```
2026-03-24 10:00:01 [INFO    ] workflow: DRY RUN mode active — no changes will be made.
2026-03-24 10:00:01 [INFO    ] workflow: Build number: 1742810401
2026-03-24 10:00:01 [INFO    ] workflow: Running pre-flight checks...
2026-03-24 10:00:01 [INFO    ] artifactory.client: DRY RUN: would GET http://172.16.1.128:8082/artifactory/api/system/ping
...
```

---

### Set up all 8 repo types

```bash
python main.py --repo-types docker npm pypi maven helm go nuget generic
```

This creates 24 repositories (8 types × 3 repos each) and pulls artifacts for every type.

---

### Set up specific types only

```bash
# Just Maven and Helm
python main.py --repo-types maven helm

# Just PyPI and NPM
python main.py --repo-types pypi npm
```

---

### Skip repo creation (repos already exist from a previous run)

```bash
python main.py --skip-repo-creation
```

---

### Pull artifacts and publish builds only — skip everything else

```bash
python main.py --skip-repo-creation --release-bundles --skip-cleanup --verbose
```

---

### Run with release bundles and save logs to a file

```bash
python main.py --release-bundles --log-file run.log
```

---

### Use a build name prefix (useful for multi-team environments)

```bash
python main.py --build-name-prefix "teamA-"
# Creates builds named: teamA-docker, teamA-npm, teamA-pypi
```

---

### Pass credentials entirely via flags / env vars (no credentials.py needed)

```bash
ARTIFACTORY_PASSWORD="Password1!" \
  python main.py --url http://172.16.1.128:8082 --username admin
```

---

### Full run with all options

```bash
python main.py \
  --repo-types docker npm pypi maven \
  --release-bundles \
  --build-name-prefix "demo-" \
  --log-file run.log \
  --verbose
```

---

## JSON Config File

For complex setups, you can store configuration in a JSON file and pass it with `--config`.

```bash
python main.py --config my_config.json
```

### Example `my_config.json`

```json
{
  "url": "http://172.16.1.128:8082",
  "username": "admin",
  "jfrog_cli_name": "my-server",
  "repo_types": ["docker", "npm", "pypi", "maven"],
  "repo_settle_sleep": 3,
  "packages": {
    "docker": ["nginx", "alpine"],
    "npm": ["express", "react"],
    "pypi": ["requests", "numpy"],
    "maven": [
      "org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.jar"
    ]
  }
}
```

> **Note:** Do not put your password in the JSON file if it will be committed anywhere. Use `ARTIFACTORY_PASSWORD` env var or `credentials.py` for the password.

### All supported JSON fields

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | Artifactory base URL |
| `username` | string | Artifactory username |
| `password` | string | Artifactory password (avoid in committed files) |
| `jfrog_cli_name` | string | JFrog CLI server ID (default: `demo-server`) |
| `repo_types` | array | List of repo types to set up |
| `repo_settle_sleep` | integer | Seconds to wait after repo creation (default: `2`) |
| `request_timeout` | integer | HTTP timeout in seconds (default: `30`) |
| `log_level` | string | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `packages` | object | Custom artifact lists per type (see example above) |

---

## Troubleshooting

### `ConfigError: Password not set`

The script cannot find your Artifactory password. Fix with one of:

```bash
# Option 1 — fill in credentials.py
echo 'ARTIFACTORY_PASSWORD = "Password1!"' >> credentials.py

# Option 2 — set env var
export ARTIFACTORY_PASSWORD="Password1!"
```

---

### `Cannot reach Artifactory at http://...`

The pre-flight check could not connect to Artifactory. Check that:
- Your Artifactory instance is running
- The URL in `credentials.py` is correct (include port if non-standard)
- No firewall / VPN is blocking the connection

---

### `Required tool 'jf' not found on PATH`

The JFrog CLI is not installed. Install it from [jfrog.com/getcli](https://jfrog.com/getcli/) and ensure `jf` is on your PATH:

```bash
jf --version   # should print a version number
```

---

### `Required tool 'docker' not found on PATH`

Docker is not installed or not running. Either install Docker, or skip the docker type:

```bash
python main.py --repo-types npm pypi   # run without docker
```

---

### A specific artifact fails to download but the rest succeed

Individual package failures are non-fatal — the script logs an `ERROR` and continues. Check the log output for the specific error, e.g.:

```
[ERROR   ] workflow: Failed to pull docker image httpd: ...
```

You can rerun with `--skip-repo-creation` to retry only the pull/build phases.

---

### Want to see every command the script is running?

```bash
python main.py --verbose
```

All `jf` and `docker` commands are logged at DEBUG level (with passwords redacted).
