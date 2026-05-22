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

    output = ""

    if result.stdout:
        print(result.stdout)
        output += result.stdout

    if result.stderr:
        print(result.stderr)
        output += "\n" + result.stderr

    return result.returncode, output


def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path, dtype=str)
    except Exception:
        return pd.DataFrame()


def make_status(combined_output: str, overall_success: bool) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_today = read_csv_safe(NEW_TODAY_CSV)
    master = read_csv_safe(MASTER_CSV)
    ranked = read_csv_safe(RANKED_CSV)
    run_log = read_csv_safe(RUN_LOG_CSV)

    quota_reached = (
        "quota" in combined_output.lower()
        or "throttle" in combined_output.lower()
        or "429" in combined_output.lower()
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

    if overall_success:
        if quota_reached:
            lines.append("## Status: Completed with SAM.gov quota/throttle stop")
            lines.append("")
            lines.append("The engine stopped because SAM.gov quota or throttling was encountered. Partial results were preserved and processed.")
        else:
            lines.append("## Status: Completed successfully")
            lines.append("")
            lines.append("The engine completed the configured daily search run without hitting quota/throttle.")
    else:
        lines.append("## Status: Failed")
        lines.append("")
        lines.append("The engine encountered an error. Review the execution output below.")

    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(f"- Active unique opportunities in master: {master_count}")
    lines.append(f"- New unique active opportunities this run: {new_count}")
    lines.append(f"- Calls made in latest fetch run: {latest_log.get('calls_made', 'Unknown')}")
    lines.append(f"- Records returned in latest fetch run: {latest_log.get('records_returned_this_run', 'Unknown')}")
    lines.append(f"- Searches run: {latest_log.get('searches', 'Unknown')}")
    lines.append("")

    if not ranked.empty and "review_priority" in ranked.columns:
        lines.append("## Actionable Pipeline Snapshot")
        lines.append("")
        for label in [
            "1 - Review Today",
            "2 - Validate Owner",
            "3 - Monitor",
            "4 - Low Priority",
            "5 - Drop",
        ]:
            count = (ranked["review_priority"] == label).sum()
            lines.append(f"- {label}: {count}")
        lines.append("")

    if not ranked.empty and "review_priority" in ranked.columns:
        actionable = ranked[
            ranked["review_priority"].isin(
                ["1 - Review Today", "2 - Validate Owner", "3 - Monitor"]
            )
        ].head(10)

        if actionable.empty:
            lines.append("## Notice")
            lines.append("")
            lines.append("No new actionable A/E opportunities were identified in this run.")
            lines.append("")
        else:
            lines.append("## Top Actionable Opportunities")
            lines.append("")
            for i, (_, row) in enumerate(actionable.iterrows(), start=1):
                lines.append(f"### {i}. {row.get('title', '')}")
                lines.append(f"- Priority: {row.get('review_priority', '')}")
                lines.append(f"- Action: {row.get('action_today', '')}")
                lines.append(f"- Score: {row.get('go_no_go_score', '')}")
                lines.append(f"- Market: {row.get('customer_market', '')}")
                lines.append(f"- Deadline: {row.get('response_deadline', '')}")
                lines.append(f"- NAICS: {row.get('clean_naics', '')}")
                lines.append(f"- Link: {row.get('ui_link', '')}")
                lines.append("")
    else:
        if new_count == 0:
            lines.append("## Notice")
            lines.append("")
            lines.append("No new unique active opportunities were found in this run.")
            lines.append("")
        else:
            lines.append("## New Opportunities Found")
            lines.append("")
            for i, (_, row) in enumerate(new_today.head(10).iterrows(), start=1):
                lines.append(f"### {i}. {row.get('title', '')}")
                lines.append(f"- Department: {row.get('department', '')}")
                lines.append(f"- Office: {row.get('office', '')}")
                lines.append(f"- Deadline: {row.get('response_deadline', '')}")
                lines.append(f"- NAICS: {row.get('naics_code', '')}")
                lines.append(f"- Link: {row.get('ui_link', '')}")
                lines.append("")

    lines.append("## Output Files")
    lines.append("")
    lines.append(f"- Master opportunity file: `{MASTER_CSV}`")
    lines.append(f"- New opportunities this run: `{NEW_TODAY_CSV}`")
    lines.append(f"- Ranked score file: `{RANKED_CSV}`")
    lines.append(f"- BD review workbook: `{REVIEW_XLSX}`")
    lines.append(f"- Summary: `{MONDAY_SUMMARY}`")
    lines.append("")

    lines.append("## Execution Output")
    lines.append("")
    lines.append("```text")
    lines.append(combined_output[-6000:])
    lines.append("```")

    STATUS_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"Daily status written to: {STATUS_MD.resolve()}")

    if overall_success:
        print("NOTICE: Daily opportunity engine completed.")
    else:
        print("NOTICE: Daily opportunity engine failed. See status report.")


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Cloud-safe path separators.
    # Start with 5 calls/day. Increase later only after the output is trusted.
    fetch_command = [
        "uv",
        "run",
        "python",
        "src/fetch_sam.py",
        "--max-calls",
        "5",
        "--days-back",
        "45",
        "--limit",
        "50",
    ]

    commands = [
        fetch_command,
        ["uv", "run", "python", "src/score_sam.py"],
        ["uv", "run", "python", "src/merge_review.py"],
        ["uv", "run", "python", "src/make_monday_summary.py"],
    ]

    combined_output = ""
    overall_success = True

    for command in commands:
        code, output = run_command(command)
        combined_output += "\n" + output

        if code != 0:
            overall_success = False
            print(f"Command failed: {' '.join(command)}")
            break

    make_status(combined_output, overall_success)

    if not overall_success:
        sys.exit(1)

    print("\nDaily opportunity engine run complete.")
    print(f"Status report: {STATUS_MD.resolve()}")


if __name__ == "__main__":
    main()