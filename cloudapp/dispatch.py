"""Delegated-mode dispatch: app repo -> central repo repository_dispatch."""

EVENT_TYPE = "cloudapp-deploy"


class DispatchError(Exception):
    pass


def dispatch_payload(app_repo, sha, manifest, environment=None):
    return {
        "event_type": EVENT_TYPE,
        "client_payload": {
            "app_repo": app_repo,
            "sha": sha,
            "manifest": manifest,
            "environment": environment or "",
        },
    }


def authorize(app_repo, allowlist):
    """Return the environments an app repo may deploy, or raise if unlisted."""
    if app_repo not in allowlist:
        raise DispatchError(f"repo '{app_repo}' is not authorized to deploy")
    return allowlist[app_repo]
