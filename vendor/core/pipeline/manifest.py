from __future__ import annotations

import hashlib
import json
import os
import subprocess

MANIFEST = "manifest.json"


class StaleArtifactError(Exception):
    pass


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def capture_run_metadata(model_versions: dict | None = None,
                          prompt_hashes: dict | None = None,
                          rejected_branches: list | None = None,
                          repo_dir: str | None = None) -> dict:
    """Snapshot the run context that write_manifest cannot infer from output
    file hashes alone: the git commit of the skill/analysis repo, the
    concrete model versions used for each agent role (config.yaml only
    records role names like "codex"/"fable", not resolved versions), a hash
    of each stage's prompt text (so a silent prompt edit is detectable even
    when the underlying model role is unchanged), and analysis branches the
    orchestrator explored but did not carry forward (so exploratory work is
    distinguishable from the confirmatory path actually reported).

    Added 2026-07-28 in response to external review: prior manifests pinned
    only output/upstream content hashes, with no record of git commit, model
    version, prompt, or rejected branches.
    """
    git_commit = None
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True,
            text=True, timeout=10, check=False,
        )
        if out.returncode == 0:
            git_commit = out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        git_commit = None

    prompt_hashes = prompt_hashes or {}
    return {
        "git_commit": git_commit,
        "model_versions": dict(model_versions or {}),
        "prompt_hashes": {k: hashlib.sha256(v.encode("utf-8")).hexdigest()
                           for k, v in prompt_hashes.items()},
        "rejected_branches": list(rejected_branches or []),
    }


def write_manifest(stage: str, stage_dir: str, upstream_manifests: list[str],
                    run_metadata: dict | None = None) -> str:
    outputs = {}
    for fn in sorted(os.listdir(stage_dir)):
        full = os.path.join(stage_dir, fn)
        if fn == MANIFEST or not os.path.isfile(full):
            continue
        outputs[fn] = _sha256(full)
    upstream = {os.path.abspath(m): _sha256(m) for m in sorted(upstream_manifests)}
    manifest = {
        "stage": stage,
        "outputs": outputs,
        "upstream": upstream,
        "run_metadata": run_metadata or {},
    }
    out_path = os.path.join(stage_dir, MANIFEST)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
    return out_path


def validate_manifest(stage_dir: str) -> None:
    with open(os.path.join(stage_dir, MANIFEST), encoding="utf-8") as fh:
        manifest = json.load(fh)
    for fn, want in manifest["outputs"].items():
        full = os.path.join(stage_dir, fn)
        if not os.path.isfile(full):
            raise StaleArtifactError(f"{stage_dir}: missing output {fn}")
        if _sha256(full) != want:
            raise StaleArtifactError(f"{stage_dir}: output {fn} changed since manifest was written")
    for m_path, want in manifest["upstream"].items():
        if not os.path.isfile(m_path):
            raise StaleArtifactError(f"{stage_dir}: upstream manifest missing: {m_path}")
        if _sha256(m_path) != want:
            raise StaleArtifactError(f"{stage_dir}: upstream {m_path} changed since it was pinned")

    # Check for unexpected files: compare current directory content to recorded outputs
    current_files = set()
    for fn in os.listdir(stage_dir):
        full = os.path.join(stage_dir, fn)
        if fn == MANIFEST or not os.path.isfile(full):
            continue
        current_files.add(fn)

    recorded_files = set(manifest["outputs"].keys())
    unexpected = current_files - recorded_files
    if unexpected:
        raise StaleArtifactError(f"{stage_dir}: unexpected file(s): {', '.join(sorted(unexpected))}")
