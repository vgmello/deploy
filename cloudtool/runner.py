"""Subprocess and network seams — inject fakes in tests."""

import subprocess
import time
import urllib.request


def run(cmd, check=True, capture=False, cwd=None):
    return subprocess.run(cmd, check=check, cwd=cwd, text=True, capture_output=capture)


def fetch_runner_ip(attempts=3, delay=5, sleep=time.sleep):
    """Public IP of this runner, or None if the lookup keeps failing."""
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen("https://api.ipify.org", timeout=10) as resp:
                return resp.read().decode().strip()
        except OSError:
            if attempt < attempts - 1:
                sleep(delay)
    return None
