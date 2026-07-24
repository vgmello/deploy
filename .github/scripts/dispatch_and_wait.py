"""Dispatch a workflow_dispatch in a target repo and wait for the run.

The pure helpers (input collection, payload/artifact/output handling, step
rendering) are importable and unit-tested; only `main()` touches the network
and the GitHub Actions environment.
"""

import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

# Give up polling after this many consecutive failures (~1 min at 10s each) so a
# persistent 404 (wrong run id) or expired token does not loop until the job's
# own timeout.
MAX_POLL_FAILURES = 6


def collect_target_inputs(environ):
    """Map INPUT_* env vars to workflow_dispatch inputs (INPUT_STACK_FILE ->
    stack_file)."""
    return {
        key[len("INPUT_"):].lower(): value
        for key, value in environ.items()
        if key.startswith("INPUT_")
    }


def build_payload(ref, inputs):
    return {"ref": ref, "inputs": inputs, "return_run_details": True}


def pick_artifact(artifacts, run_id):
    """The deployment-outputs artifact for this run, or None."""
    name = f"deployment-outputs-{run_id}"
    return next((a for a in artifacts if a.get("name") == name), None)


def extract_results(zip_bytes):
    """Read deployment-results.json out of the artifact zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf, zf.open("deployment-results.json") as f:
        return json.load(f)


def format_output_lines(results):
    """key=value lines for $GITHUB_OUTPUT, one per result field."""
    return "".join(f"{key}={value}\n" for key, value in results.items())


def render_step(step):
    """Display line for a target step transition, or None if not worth printing."""
    if step["status"] == "in_progress":
        return f"  Running step: {step['name']}..."
    if step["status"] == "completed":
        mark = "ok" if step.get("conclusion") == "success" else "FAILED"
        return f"  [{mark}] {step['name']}"
    return None


def step_key(job, step):
    return f"{job['id']}_{step['name']}_{step['status']}"


def main():
    owner = os.environ["TARGET_OWNER"]
    repo = os.environ["TARGET_REPO"]
    workflow_id = os.environ["TARGET_WORKFLOW"]
    branch = os.environ.get("TARGET_BRANCH", "main")
    token = os.environ["GH_TOKEN"]

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }

    def get(url):
        return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=headers)).read().decode("utf-8"))

    target_inputs = collect_target_inputs(os.environ)
    print(f"Target: {owner}/{repo} -> {workflow_id} (Branch: {branch})")
    print(f"Workflow Inputs: {target_inputs}")

    dispatch_url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches"
    dispatch_req = urllib.request.Request(
        dispatch_url,
        data=json.dumps(build_payload(branch, target_inputs)).encode("utf-8"),
        headers=headers,
        method="POST",
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

    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as fh:
            fh.write(f"TARGET_RUN_URL={run_html_url}\n")

    def expose_deployment_outputs():
        gh_output = os.environ.get("GITHUB_OUTPUT")
        if not gh_output:
            return
        artifacts_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts"
        try:
            artifacts = get(artifacts_url).get("artifacts", [])
        except Exception as exc:
            print(f"::warning::could not list artifacts for run {run_id}: {exc}")
            return
        target = pick_artifact(artifacts, run_id)
        if not target:
            print("::warning::no deployment-outputs artifact on the target run")
            return
        try:
            with urllib.request.urlopen(urllib.request.Request(target["archive_download_url"], headers=headers)) as resp:
                results = extract_results(resp.read())
        except Exception as exc:
            print(f"::warning::could not download/parse deployment outputs: {exc}")
            return
        with open(gh_output, "a") as out:
            out.write(format_output_lines(results))
        print(f"Exposed deployment outputs: {results}")

    poll_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
    poll_req = urllib.request.Request(poll_url, headers=headers)
    jobs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"

    def stream_steps(seen):
        try:
            jobs_data = get(jobs_url)
        except Exception:
            return
        for job in jobs_data.get("jobs", []):
            for step in job.get("steps", []):
                key = step_key(job, step)
                if key in seen:
                    continue
                seen.add(key)
                line = render_step(step)
                if line:
                    print(line)

    last_status = None
    poll_failures = 0
    seen_steps = set()
    while True:
        try:
            with urllib.request.urlopen(poll_req) as resp:
                run_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
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

        if status != last_status:
            if status == "queued":
                print("Status: queued (waiting for concurrent deployment lock)...")
            else:
                print(f"Status: {status}...")
            last_status = status

        stream_steps(seen_steps)

        if status == "completed":
            print(f"\nTarget workflow complete: {(conclusion or 'unknown').upper()}")
            print(f"View logs: {run_data.get('html_url', '')}")
            expose_deployment_outputs()
            if conclusion != "success":
                sys.exit(1)
            break

        time.sleep(10)


if __name__ == "__main__":
    main()
