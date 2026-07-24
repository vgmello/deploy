"""Deploy identity model: federation subjects and login sequencing.

Pure functions — the security-critical mapping from (event, mode) to which
managed identity signs in for which phase, and to the OIDC subject each
identity's federated credential must trust.
"""

MODES = ("self", "delegated")
DEPLOY_IDENTITIES = ("plan", "apply")
EVENTS = ("pull_request", "default_branch")


def federation_subjects(mi, mode, app_repo, central_repo, env):
    """OIDC subjects a per-tool MI's federated credentials must trust."""
    if mode not in MODES:
        raise ValueError(f"unknown mode '{mode}'")
    if mi not in DEPLOY_IDENTITIES:
        raise ValueError(f"unknown deploy identity '{mi}'")

    if mode == "self":
        if mi == "plan":
            return [f"repo:{app_repo}:pull_request", f"repo:{app_repo}:environment:{env}"]
        return [f"repo:{app_repo}:environment:{env}"]
    # delegated: only the central repo's subjects, never the app repo
    if mi == "plan":
        return [f"repo:{central_repo}:environment:{env}-plan"]
    return [f"repo:{central_repo}:environment:{env}"]


def login_plan(event, backend_type):
    """Ordered deploy phases for an event. Each phase names the identity that
    signs in, the terraform action, the stack, and whether the state backend
    needs its own (AWS) OIDC login this phase."""
    if event not in EVENTS:
        raise ValueError(f"unknown event '{event}'")
    state_login = backend_type == "s3"

    if event == "pull_request":
        phases = [{"identity": "plan", "action": "plan", "stack": "main"}]
    else:
        phases = [
            {"identity": "bootstrap", "action": "apply", "stack": "bootstrap"},
            {"identity": "plan", "action": "plan", "stack": "main"},
            {"identity": "apply", "action": "apply", "stack": "main"},
        ]
    for p in phases:
        p["state_login"] = state_login
    return phases
