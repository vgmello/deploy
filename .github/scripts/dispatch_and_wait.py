import json
import os
import sys
import time
import urllib.error
import urllib.request

OWNER = os.environ["TARGET_OWNER"]
REPO = os.environ["TARGET_REPO"]
WORKFLOW_ID = os.environ["TARGET_WORKFLOW"]
BRANCH = os.environ.get("TARGET_BRANCH", "main")
TOKEN = os.environ["GH_TOKEN"]

# Extract target inputs dynamically from environment (INPUT_REPO, INPUT_STACK_FILE, etc.)
target_inputs = {}
for env_key, env_value in os.environ.items():
    if env_key.startswith("INPUT_"):
        # Converts 'INPUT_STACK_FILE' -> 'stack_file'
        input_name = env_key.replace("INPUT_", "").lower()
        target_inputs[input_name] = env_value

print(f"Target: {OWNER}/{REPO} -> {WORKFLOW_ID} (Branch: {BRANCH})")
print(f"Workflow Inputs: {target_inputs}")

# Setup API URL and Headers
url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows/{WORKFLOW_ID}/dispatches"
headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json",
}

payload = {
    "ref": BRANCH,
    "inputs": target_inputs,
    "return_run_details": True,
}

# 1. Trigger Dispatch
dispatch_req = urllib.request.Request(
    url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
)

try:
    with urllib.request.urlopen(dispatch_req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
    sys.exit(1)

run_id = data["workflow_run_id"]
print(f"\nDispatched successfully! Run ID: {run_id}")
print(f"Run URL: {data.get('html_url', '')}")

# 2. Poll Status
poll_url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/runs/{run_id}"
poll_req = urllib.request.Request(poll_url, headers=headers)

while True:
    try:
        with urllib.request.urlopen(poll_req) as resp:
            run_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"Status poll error: {e}")
        time.sleep(10)
        continue

    status = run_data["status"]
    conclusion = run_data.get("conclusion")
    print(f"Status: {status}...")

    if status == "completed":
        print(f"\nWorkflow finished with conclusion: {conclusion}")
        if conclusion != "success":
            sys.exit(1)  # Fails the composite action step
        break

    time.sleep(10)
