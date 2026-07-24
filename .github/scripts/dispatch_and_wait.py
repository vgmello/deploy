import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

OWNER = os.environ["TARGET_OWNER"]
REPO = os.environ["TARGET_REPO"]
WORKFLOW_ID = os.environ["TARGET_WORKFLOW"]
BRANCH = os.environ.get("TARGET_BRANCH", "main")
TOKEN = os.environ["GH_TOKEN"]

# Give up polling after this many consecutive failures (~1 min at 10s each) so a
# persistent 404 (wrong run id) or expired token does not loop until the job's
# own timeout.
MAX_POLL_FAILURES = 6

# Extract target inputs dynamically from environment (INPUT_REPO, INPUT_STACK_FILE, etc.)
target_inputs = {}
for env_key, env_value in os.environ.items():
    if env_key.startswith("INPUT_"):
        input_name = env_key.replace("INPUT_", "").lower()
        target_inputs[input_name] = env_value

print(f"Target: {OWNER}/{REPO} -> {WORKFLOW_ID} (Branch: {BRANCH})")
print(f"Workflow Inputs: {target_inputs}")

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
    print(f"::error::HTTP Error {e.code}: {e.read().decode('utf-8')}")
    sys.exit(1)

run_id = data["workflow_run_id"]
run_html_url = data.get("html_url", "")
print(f"\nDispatched successfully! Run ID: {run_id}")
print(f"Run URL: {run_html_url}")

# Publish the target run URL so a later composite step (e.g. a caller summary)
# can reference it via env.TARGET_RUN_URL.
github_env = os.environ.get("GITHUB_ENV")
if github_env:
    with open(github_env, "a") as fh:
        fh.write(f"TARGET_RUN_URL={run_html_url}\n")


def expose_deployment_outputs():
    """Download the target run's deployment-outputs artifact and expose the
    fields of deployment-results.json as this step's outputs. Best-effort —
    a missing artifact or download error must not fail the dispatch."""
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if not gh_output:
        return
    artifacts_url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/runs/{run_id}/artifacts"
    try:
        with urllib.request.urlopen(urllib.request.Request(artifacts_url, headers=headers)) as resp:
            artifacts = json.loads(resp.read().decode("utf-8")).get("artifacts", [])
    except Exception as exc:
        print(f"::warning::could not list artifacts for run {run_id}: {exc}")
        return
    target = next((a for a in artifacts if a["name"] == f"deployment-outputs-{run_id}"), None)
    if not target:
        print("::warning::no deployment-outputs artifact on the target run")
        return
    try:
        with urllib.request.urlopen(urllib.request.Request(target["archive_download_url"], headers=headers)) as resp:
            blob = resp.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as zf, zf.open("deployment-results.json") as f:
            results = json.load(f)
    except Exception as exc:
        print(f"::warning::could not download/parse deployment outputs: {exc}")
        return
    with open(gh_output, "a") as out:
        for key, value in results.items():
            out.write(f"{key}={value}\n")
    print(f"Exposed deployment outputs: {results}")

# 2. Poll Status
poll_url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/runs/{run_id}"
poll_req = urllib.request.Request(poll_url, headers=headers)
jobs_url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/runs/{run_id}/jobs"
jobs_req = urllib.request.Request(jobs_url, headers=headers)


def stream_steps(seen):
    """Print each target job step once as it starts and finishes. Best-effort:
    the jobs API lagging or erroring must not interrupt polling."""
    try:
        with urllib.request.urlopen(jobs_req) as resp:
            jobs_data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return
    for job in jobs_data.get("jobs", []):
        for step in job.get("steps", []):
            key = f"{job['id']}_{step['name']}_{step['status']}"
            if key in seen:
                continue
            seen.add(key)
            if step["status"] == "in_progress":
                print(f"  Running step: {step['name']}...")
            elif step["status"] == "completed":
                mark = "ok" if step.get("conclusion") == "success" else "FAILED"
                print(f"  [{mark}] {step['name']}")


last_status = None
poll_failures = 0
seen_steps = set()
while True:
    try:
        with urllib.request.urlopen(poll_req) as resp:
            run_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 401/403 are auth failures — the token will not recover, so stop now.
        if e.code in (401, 403):
            print(f"::error::Auth failed polling run {run_id} ({e.code}); token invalid or lacks access")
            sys.exit(1)
        poll_failures += 1
        if poll_failures >= MAX_POLL_FAILURES:
            print(f"::error::Gave up polling run {run_id} after {poll_failures} consecutive failures (last {e.code})")
            sys.exit(1)
        print(f"Status poll warning ({e.code}), retry {poll_failures}/{MAX_POLL_FAILURES} in 10s...")
        time.sleep(10)
        continue

    poll_failures = 0
    status = run_data["status"]
    conclusion = run_data.get("conclusion")

    # Provide clear feedback when job is queued waiting for concurrency lock
    if status != last_status:
        if status == "queued":
            print("Status: queued (waiting for concurrent deployment lock)...")
        else:
            print(f"Status: {status}...")
        last_status = status

    # Stream individual step transitions from the target run.
    stream_steps(seen_steps)

    if status == "completed":
        print(f"\nTarget workflow complete: {(conclusion or 'unknown').upper()}")
        print(f"View logs: {run_data.get('html_url', '')}")
        expose_deployment_outputs()
        if conclusion != "success":
            sys.exit(1)
        break

    time.sleep(10)
