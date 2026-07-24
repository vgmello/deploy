import pytest

from cloudapp import identity


def test_self_mode_plan_subjects_reference_app_repo():
    subs = identity.federation_subjects(
        "plan", "self", app_repo="acme/orders", central_repo="vgmello/deploy", env="prod"
    )
    assert subs == [
        "repo:acme/orders:pull_request",
        "repo:acme/orders:environment:prod",
    ]


def test_self_mode_apply_subject_is_environment_only():
    subs = identity.federation_subjects(
        "apply", "self", app_repo="acme/orders", central_repo="vgmello/deploy", env="prod"
    )
    assert subs == ["repo:acme/orders:environment:prod"]


def test_delegated_mode_plan_uses_central_plan_environment():
    subs = identity.federation_subjects(
        "plan", "delegated", app_repo="acme/orders", central_repo="vgmello/deploy", env="prod"
    )
    assert subs == ["repo:vgmello/deploy:environment:prod-plan"]


def test_delegated_mode_apply_uses_central_environment():
    subs = identity.federation_subjects(
        "apply", "delegated", app_repo="acme/orders", central_repo="vgmello/deploy", env="prod"
    )
    assert subs == ["repo:vgmello/deploy:environment:prod"]


def test_delegated_mode_never_references_app_repo():
    for mi in ("plan", "apply"):
        subs = identity.federation_subjects(
            mi, "delegated", app_repo="acme/orders", central_repo="vgmello/deploy", env="prod"
        )
        assert all("acme/orders" not in s for s in subs)


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
