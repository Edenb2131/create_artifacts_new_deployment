from dataclasses import dataclass, field


@dataclass
class RepoDefinition:
    package_type: str
    remote_url: str
    local_name: str
    remote_name: str
    virtual_name: str
    local_extra: dict = field(default_factory=dict)
    remote_extra: dict = field(default_factory=dict)
    virtual_extra: dict = field(default_factory=dict)


REPO_DEFINITIONS: dict[str, RepoDefinition] = {
    "docker": RepoDefinition(
        package_type="docker",
        remote_url="https://registry-1.docker.io",
        local_name="docker-local",
        remote_name="docker-remote",
        virtual_name="docker-virtual",
        remote_extra={"enableTokenAuthentication": True},
    ),
    "npm": RepoDefinition(
        package_type="npm",
        remote_url="https://registry.npmjs.org",
        local_name="npm-local",
        remote_name="npm-remote",
        virtual_name="npm-virtual",
    ),
    "pypi": RepoDefinition(
        package_type="pypi",
        remote_url="https://files.pythonhosted.org",
        local_name="pypi-local",
        remote_name="pypi-remote",
        virtual_name="pypi-virtual",
    ),
    "maven": RepoDefinition(
        package_type="maven",
        remote_url="https://repo1.maven.org/maven2",
        local_name="maven-local",
        remote_name="maven-remote",
        virtual_name="maven-virtual",
        local_extra={"repoLayoutRef": "maven-2-default"},
        remote_extra={"repoLayoutRef": "maven-2-default"},
        virtual_extra={
            "repoLayoutRef": "maven-2-default",
            "pomRepositoryReferencesCleanupPolicy": "discard_active_reference",
        },
    ),
    "helm": RepoDefinition(
        package_type="helm",
        remote_url="https://charts.bitnami.com/bitnami",
        local_name="helm-local",
        remote_name="helm-remote",
        virtual_name="helm-virtual",
    ),
    "go": RepoDefinition(
        package_type="go",
        remote_url="https://goproxy.io",
        local_name="go-local",
        remote_name="go-remote",
        virtual_name="go-virtual",
    ),
    "nuget": RepoDefinition(
        package_type="nuget",
        remote_url="https://www.nuget.org",
        local_name="nuget-local",
        remote_name="nuget-remote",
        virtual_name="nuget-virtual",
    ),
    "generic": RepoDefinition(
        package_type="generic",
        remote_url="https://releases.hashicorp.com",
        local_name="generic-local",
        remote_name="generic-remote",
        virtual_name="generic-virtual",
    ),
}
