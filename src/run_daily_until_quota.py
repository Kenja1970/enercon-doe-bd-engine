import subprocess
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd


REPORTS_DIR = Path("reports")
RAW_DIR = Path("data/raw")

STATUS_MD = REPORTS_DIR / "daily_run_status.md"
RUN_LOG_CSV = RAW_DIR / "sam_run_log.csv"
NEW_TODAY_CSV = RAW_DIR / "sam_new_unique_today.csv"
MASTER_CSV = RAW_DIR / "sam_active_master.csv"
RANKED_CSV = REPORTS_DIR / "sam_go_no_go_ranked.csv"
REVIEW_XLSX = REPORTS_DIR / "sam_go_no_go_with_review.xlsx"
MONDAY_SUMMARY = REPORTS_DIR / "monday_bd_summary.md"


def run_command(command: list[str]) -> tuple[int, str]:
    print("\nRunning:", " ".join(command))

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=False,
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print(result.stderr)

    return result.returncode, result.stdout + "\n" + result.stderr


def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path, dtype=str)
    except Exception:
        return pd.DataFrame()


def make_status(fetch_output: str) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_today = read_csv_safe(NEW_TODAY_CSV)
    master = read_csv_safe(MASTER_CSV)
    ranked = read_csv_safe(RANKED_CSV)
    run_log = read_csv_safe(RUN_LOG_CSV)

    quota_reached = (
        "quota" in fetch_output.lower()
        or "throttle" in fetch_output.lower()
        or "429" in fetch_output.lower()
    )

    latest_log = {}
    if not run_log.empty:
        latest_log = run_log.iloc[-1].to_dict()

    new_count = len(new_today)
    master_count = len(master)

    lines = []
    lines.append("# Daily A/E Opportunity Engine Status")
    lines.append("")
    lines.append(f"Run completed: {run_date}")
    lines.append("")

    if quota_reached:
        lines.append("## Status: SAM.gov quota/throttle reached")
        lines.append("")
        lines.append("The engine stopped because SAM.gov quota or throttling was encountered. Partial results were preserved and processed.")
    else:
        lines.append("## Status: Run completed without quota stop")
        lines.append("")
        lines.append("The engine completed the available search stack or used cached results without hitting the quota limit.")

    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(f"- Active unique opportunities in master: {master_count}")
    lines.append(f"- New unique active opportunities this run: {new_count}")
    lines.append(f"- Calls made in latest fetch run: {latest_log.get('calls_made', 'Unknown')}")
    lines.append(f"- Records returned in latest fetch run: {latest_log.get('records_returned_this_run', 'Unknown')}")
    lines.append(f"- Searches run: {latest_log.get('searches', 'Unknown')}")
    lines.append("")

    if new_count == 0:
        lines.append("## Notice")
        lines.append("")
        lines.append("No new unique active A/E opportunities were found in this run.")
        lines.append("")
    else:
        lines.append("## New Opportunities Found")
        lines.append("")
        preview_cols = [
            "title",
            "department",
            "office",
            "response_deadline",
            "naics_code",
            "ui_link",
        ]
        available_cols = [c for c in preview_cols if c in new_today.columns]

        for i, (_, row) in enumerate(new_today.head(10).iterrows(), start=1):
            lines.append(f"### {i}. {row.get('title', '')}")
            lines.append(f"- Department: {row.get('department', '')}")
            lines.append(f"- Office: {row.get('office', '')}")
            lines.append(f"- Deadline: {row.get('response_deadline', '')}")
            lines.append(f"- NAICS: {row.get('naics_code', '')}")
            lines.append(f"- Link: {row.get('ui_link', '')}")
            lines.append("")

    if not ranked.empty and "recommendation" in ranked.columns:
        lines.append("## Scored Pipeline Snapshot")
        lines.append("")
        for label in [
            "Pursue / Discuss Monday",
            "Strong Monitor / Validate Owner",
            "Monitor / Shape",
            "Low Priority",
            "No-Go",
        ]:
            count = (ranked["recommendation"] == label).sum()
            lines.append(f"- {label}: {count}")

        lines.append("")

    lines.append("## Output Files")
    lines.append("")
    lines.append(f"- Master opportunity file: `{MASTER_CSV}`")
    lines.append(f"- New opportunities this run: `{NEW_TODAY_CSV}`")
    lines.append(f"- Ranked score file: `{RANKED_CSV}`")
    lines.append(f"- BD review workbook: `{REVIEW_XLSX}`")
    lines.append(f"- Summary: `{MONDAY_SUMMARY}`")
    lines.append("")

    STATUS_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"Daily status written to: {STATUS_MD.resolve()}")

    if new_count == 0:
        print("NOTICE: No new unique active A/E opportunities were found.")
    else:
        print(f"NOTICE: {new_count} new unique active opportunities found.")

    if quota_reached:
        print("NOTICE: SAM.gov quota/throttle was reached. Partial results were preserved.")


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # High max-calls intentionally allows fetch_sam.py to continue until
    # SAM.gov quota/throttle is reached or the search stack is exhausted.
    fetch_command = [
        "uv",
        "run",
        "python",
        "src\\fetch_sam.py",
        "--max-calls",
        "999",
        "--days-back",
        "45",
        "--limit",
        "50",
    ]

    fetch_code, fetch_output = run_command(fetch_command)

    # Even if fetch hits quota, continue processing whatever data was saved.
    if fetch_code != 0:
        print("Fetch command returned a non-zero exit code. Continuing to process saved data.")

    commands = [
        ["uv", "run", "python", "src\\score_sam.py"],
        ["uv", "run", "python", "src\\merge_review.py"],
        ["uv", "run", "python", "src\\make_monday_summary.py"],
    ]

    combined_output = fetch_output

    for command in commands:
        code, output = run_command(command)
        combined_output += "\n" + output

        if code != 0:
            print(f"Command failed: {' '.join(command)}")
            make_status(combined_output)
            sys.exit(code)

    make_status(combined_output)

    print("\nDaily opportunity engine run complete.")
    print(f"Status report: {STATUS_MD.resolve()}")


if __name__ == "__main__":
    main()