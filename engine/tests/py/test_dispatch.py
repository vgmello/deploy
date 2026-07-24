import pytest

from cloudapp import dispatch


def test_payload_shape():
    p = dispatch.dispatch_payload("acme/orders", "abc123", ".cloud-app.yml")
    assert p == {
        "event_type": "cloudapp-deploy",
        "client_payload": {
            "app_repo": "acme/orders",
            "sha": "abc123",
            "manifest": ".cloud-app.yml",
            "environment": "",
        },
    }


def test_payload_carries_single_environment_filter():
    p = dispatch.dispatch_payload("acme/orders", "abc123", ".cloud-app.yml", environment="dev")
    assert p["client_payload"]["environment"] == "dev"


def test_authorize_returns_mapped_environments():
    allowlist = {"acme/orders": ["dev", "prod"]}
    assert dispatch.authorize("acme/orders", allowlist) == ["dev", "prod"]


def test_authorize_rejects_unlisted_repo():
    with pytest.raises(dispatch.DispatchError, match="not authorized"):
        dispatch.authorize("evil/repo", {"acme/orders": ["dev"]})
