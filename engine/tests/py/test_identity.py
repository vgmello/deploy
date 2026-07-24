import pytest

from cloudapp import identity


def test_self_mode_plan_subjects_reference_app_repo():
    subs = identity.federation_subjects(
        "plan", "self", app_repo="acme/orders", central_repo="vgmello/cloud-app", env="prod"
    )
    assert subs == [
        "repo:acme/orders:pull_request",
        "repo:acme/orders:environment:prod",
    ]


def test_self_mode_apply_subject_is_environment_only():
    subs = identity.federation_subjects(
        "apply", "self", app_repo="acme/orders", central_repo="vgmello/cloud-app", env="prod"
    )
    assert subs == ["repo:acme/orders:environment:prod"]


def test_delegated_mode_plan_federates_to_caller():
    subs = identity.federation_subjects(
        "plan", "delegated", app_repo="acme/orders", central_repo="vgmello/cloud-app", env="prod"
    )
    assert subs == ["repo:acme/orders:pull_request", "repo:acme/orders:environment:prod"]


def test_delegated_mode_apply_federates_to_caller():
    subs = identity.federation_subjects(
        "apply", "delegated", app_repo="acme/orders", central_repo="vgmello/cloud-app", env="prod"
    )
    assert subs == ["repo:acme/orders:environment:prod"]


def test_delegated_mode_never_references_central_repo():
    # Split topology: the caller runs plan/apply, so those identities federate to
    # the app repo and never to the control repo.
    for mi in ("plan", "apply"):
        subs = identity.federation_subjects(
            mi, "delegated", app_repo="acme/orders", central_repo="vgmello/cloud-app", env="prod"
        )
        assert all("vgmello/cloud-app" not in s for s in subs)


def test_unknown_mode_or_mi_fails():
    with pytest.raises(ValueError):
        identity.federation_subjects("plan", "trustme", "a/b", "c/d", "dev")
    with pytest.raises(ValueError):
        identity.federation_subjects("bootstrap", "self", "a/b", "c/d", "dev")


def test_pr_event_is_plan_only():
    phases = identity.login_plan("pull_request", "azurerm")
    assert phases == [
        {"identity": "plan", "action": "plan", "stack": "main", "state_login": False},
    ]


def test_default_branch_runs_bootstrap_plan_apply():
    phases = identity.login_plan("default_branch", "azurerm")
    assert [p["identity"] for p in phases] == ["bootstrap", "plan", "apply"]
    assert [p["action"] for p in phases] == ["apply", "plan", "apply"]
    assert [p["stack"] for p in phases] == ["bootstrap", "main", "main"]


def test_s3_backend_marks_every_phase_for_aws_state_login():
    for event in ("pull_request", "default_branch"):
        phases = identity.login_plan(event, "s3")
        assert all(p["state_login"] for p in phases)
    assert all(not p["state_login"] for p in identity.login_plan("default_branch", "azurerm"))


def test_unknown_event_fails():
    with pytest.raises(ValueError):
        identity.login_plan("tag_push", "azurerm")


def test_subject_components_are_validated():
    # env with a colon could inject an extra subject claim
    with pytest.raises(ValueError):
        identity.federation_subjects("plan", "self", "acme/orders", "vgmello/cloud-app", "prod:evil")
    # wildcard env
    with pytest.raises(ValueError):
        identity.federation_subjects("apply", "self", "acme/orders", "vgmello/cloud-app", "*")
    # malformed repo (no slash)
    with pytest.raises(ValueError):
        identity.federation_subjects("plan", "self", "notarepo", "vgmello/cloud-app", "prod")
