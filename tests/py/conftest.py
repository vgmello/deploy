import json
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).parents[2]
sys.path.insert(0, str(REPO))

FIXTURES = REPO / "tests" / "fixtures" / "manifests"
GOLDEN = REPO / "tests" / "golden"
ENVDIR = REPO / "tests" / "fixtures" / "environments"


@pytest.fixture
def repo():
    return REPO


def load_manifest(name):
    return yaml.safe_load((FIXTURES / f"{name}.yml").read_text())


def load_golden(name):
    return json.loads((GOLDEN / f"{name}.json").read_text())


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRunner:
    """Records commands; per-command results configured by prefix match."""

    def __init__(self, results=None):
        self.calls = []
        self.results = results or []

    def __call__(self, cmd, check=True, capture=False, cwd=None):
        self.calls.append(list(cmd))
        for prefix, result in self.results:
            if cmd[: len(prefix)] == list(prefix):
                if callable(result):
                    result = result(cmd)
                if check and result.returncode != 0:
                    raise RuntimeError(f"command failed: {cmd}")
                return result
        return FakeResult()

    def commands(self, *prefix):
        return [c for c in self.calls if c[: len(prefix)] == list(prefix)]
