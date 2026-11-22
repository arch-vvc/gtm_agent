import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "eval.yml"
RUN_LINES = [
    "uv run pytest -q",
    "uv run ruff check .",
    "uv run python -m scripts.golden_eval --csv results/eval_results.csv --floor-file evals/floor.json",
]


def run_lines(text):
    return [line.split("run:", 1)[1].strip() for line in text.splitlines() if line.strip().lstrip("- ").startswith("run:")]


def test_workflow_has_no_secrets_and_runs_the_gate():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "push" in text and "pull_request" in text
    assert "secrets." not in text
    assert "GEMINI" not in text and "GROQ" not in text
    assert run_lines(text) == RUN_LINES


def test_the_gate_commands_pass_locally():
    # pytest itself is skipped here: running it from inside pytest would recurse.
    ruff = subprocess.run([sys.executable, "-m", "ruff", "check", "."], cwd=ROOT, check=False, capture_output=True, text=True)
    gate = subprocess.run(
        [sys.executable, "-m", "scripts.golden_eval", "--csv", "results/eval_results.csv", "--floor-file", "evals/floor.json"],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )  # fmt: skip

    assert ruff.returncode == 0, ruff.stdout
    assert gate.returncode == 0, gate.stdout
