from pathlib import Path

import pandas as pd


INPUT_CSV = Path("reports/sam_go_no_go_with_review.csv")
OUTPUT_MD = Path("reports/monday_bd_summary.md")


def val(row, col):
    value = row.get(col, "")
    if pd.isna(value):
        return ""
    return str(value)


def main() -> None:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_CSV}")

    df = pd.read_csv(INPUT_CSV, dtype=str)

    if "go_no_go_score" in df.columns:
        df["score_num"] = pd.to_numeric(df["go_no_go_score"], errors="coerce").fillna(0)
        df = df.sort_values("score_num", ascending=False)

    priority = df[
        df["recommendation"].isin(
            ["Pursue / Discuss Monday", "Strong Monitor / Validate Owner"]
        )
    ].head(10)

    monitor = df[df["recommendation"] == "Monitor / Shape"].head(10)

    lines = []

    lines.append("# DOE/Federal BD Monday Summary")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- Total active opportunities in master/review file: {len(df)}")
    lines.append(f"- Priority candidates: {len(priority)}")
    lines.append(f"- Monitor candidates shown: {len(monitor)}")
    lines.append("- Recommended use: confirm owner, relationship position, Salesforce action, and pursuit decision.")
    lines.append("")

    lines.append("## Top Priority Opportunities")
    lines.append("")

    if priority.empty:
        lines.append("No priority opportunities identified.")
        lines.append("")
    else:
        for i, (_, row) in enumerate(priority.iterrows(), start=1):
            lines.append(f"### {i}. {val(row, 'title')}")
            lines.append(f"- Score: {val(row, 'go_no_go_score')}")
            lines.append(f"- Recommendation: {val(row, 'recommendation')}")
            lines.append(f"- Pursuit type: {val(row, 'pursuit_type')}")
            lines.append(f"- Customer/Office: {val(row, 'department')} / {val(row, 'office')}")
            lines.append(f"- Deadline: {val(row, 'response_deadline')}")
            lines.append(f"- Days until deadline: {val(row, 'days_until_deadline')}")
            lines.append(f"- BD owner: {val(row, 'bd_owner')}")
            lines.append(f"- Relationship owner: {val(row, 'relationship_owner')}")
            lines.append(f"- Salesforce action: {val(row, 'salesforce_action')}")
            lines.append(f"- Risk flags: {val(row, 'risk_flags')}")
            lines.append(f"- Link: {val(row, 'ui_link')}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Monitor / Shape Candidates")
    lines.append("")

    if monitor.empty:
        lines.append("No monitor candidates identified.")
        lines.append("")
    else:
        for i, (_, row) in enumerate(monitor.iterrows(), start=1):
            lines.append(f"### {i}. {val(row, 'title')}")
            lines.append(f"- Score: {val(row, 'go_no_go_score')}")
            lines.append(f"- Customer/Office: {val(row, 'department')} / {val(row, 'office')}")
            lines.append(f"- Deadline: {val(row, 'response_deadline')}")
            lines.append(f"- Link: {val(row, 'ui_link')}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Monday Decisions Needed")
    lines.append("")
    lines.append("1. Which opportunities should be entered or updated in Salesforce?")
    lines.append("2. Who owns the customer relationship?")
    lines.append("3. Are we prime, sub, or teaming partner?")
    lines.append("4. Which opportunities should be dropped immediately?")
    lines.append("5. Which items need ENERCON/Pond capability alignment?")
    lines.append("")

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"Monday summary saved: {OUTPUT_MD.resolve()}")


if __name__ == "__main__":
    main()