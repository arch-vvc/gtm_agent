import csv
from pathlib import Path

from scripts import export_public

ROOT = Path(__file__).resolve().parent.parent
# Every row here is SYNTHETIC.
FULL_HEADER = ["url", "name", "cluster", "demo", "hiring_fde", "cluster_reason", "customer_pain", "tailoring",
               "pitch_note", "pitch_error", "model", "error", "evidence"]  # fmt: skip
PUBLIC_HEADER = ["url", "name", "cluster", "demo", "hiring_fde", "cluster_reason", "model", "error", "has_note",
                 "pitch_error"]  # fmt: skip


def test_no_note_or_tailoring_text_in_public_csv(tmp_path):
    full = tmp_path / "full.csv"
    with open(full, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(FULL_HEADER)
        writer.writerow(["a.example", "A", "A", "d", "true", "A does x.", "PAINTEXT", "TAILORTEXT", "NOTETEXT", "", "m", "", "EVIDENCETEXT"])
        writer.writerow(["b.example", "B", "", "", "", "", "", "", "", "", "", "Could not reach site", ""])
    out = tmp_path / "public.csv"

    assert export_public.main(["--csv", str(full), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    rows = list(csv.DictReader(text.splitlines()))

    for secret in ("PAINTEXT", "TAILORTEXT", "NOTETEXT", "EVIDENCETEXT"):
        assert secret not in text
    assert list(rows[0]) == PUBLIC_HEADER
    assert [row["has_note"] for row in rows] == ["true", "false"]
    assert rows[1]["error"] == "Could not reach site"


def test_the_committed_public_csv_has_no_note_columns():
    with open(ROOT / "results" / "eval_results.csv", encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))

    assert header == PUBLIC_HEADER
