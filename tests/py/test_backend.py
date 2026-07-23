import pytest

from cloudapp import backend
from conftest import ENVDIR


def test_renders_backend_config_with_per_tool_state_key():
    assert backend.render(ENVDIR / "dev.yml", "orders-api", "dev") == [
        "resource_group_name=rg-tfstate",
        "storage_account_name=sttfstatedev",
        "container_name=tfstate",
        "key=orders-api/dev.tfstate",
        "use_oidc=true",
        "use_azuread_auth=true",
    ]


def test_missing_terraform_state_key_fails(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("location: eastus2\n")
    with pytest.raises(backend.BackendError, match="terraform_state.resource_group"):
        backend.render(bad, "orders-api", "dev")
