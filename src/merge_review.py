from pathlib import Path

import pandas as pd


REPORTS_DIR = Path("reports")
RAW_DIR = Path("data/raw")

SCORED_CSV = REPORTS_DIR / "sam_go_no_go_ranked.csv"
REVIEW_CSV = RAW_DIR / "bd_review_tracker.csv"
OUTPUT_XLSX = REPORTS_DIR / "sam_go_no_go_with_review.xlsx"
OUTPUT_CSV = REPORTS_DIR / "sam_go_no_go_with_review.csv"


REVIEW_COLUMNS = [
    "notice_id",
    "manual_decision",
    "bd_owner",
    "relationship_owner",
    "salesforce_action",
    "prime_sub_team",
    "manual_notes",
    "last_reviewed",
]


def main() -> None:
    if not SCORED_CSV.exists():
        raise FileNotFoundError(f"Missing scored file: {SCORED_CSV}")

    scored = pd.read_csv(SCORED_CSV, dtype=str)

    if "notice_id" not in scored.columns:
        raise ValueError("Scored file does not contain notice_id column.")

    scored["notice_id"] = scored["notice_id"].astype(str)

    if REVIEW_CSV.exists():
        review = pd.read_csv(REVIEW_CSV, dtype=str)
    else:
        review = pd.DataFrame(columns=REVIEW_COLUMNS)

    for col in REVIEW_COLUMNS:
        if col not in review.columns:
            review[col] = ""

    review["notice_id"] = review["notice_id"].astype(str)

    existing_ids = set(review["notice_id"].dropna().astype(str))
    scored_ids = scored["notice_id"].dropna().astype(str).unique()

    new_ids = [x for x in scored_ids if x not in existing_ids]

    if new_ids:
        new_rows = pd.DataFrame({"notice_id": new_ids})
        for col in REVIEW_COLUMNS:
            if col not in new_rows.columns:
                new_rows[col] = ""
        review = pd.concat([review, new_rows[REVIEW_COLUMNS]], ignore_index=True)
        review.to_csv(REVIEW_CSV, index=False)

    merged = scored.merge(review[REVIEW_COLUMNS], on="notice_id", how="left")

    front_cols = [
        "manual_decision",
        "salesforce_action",
        "bd_owner",
        "relationship_owner",
        "prime_sub_team",
        "manual_notes",
        "last_reviewed",
        "go_no_go_score",
        "recommendation",
        "pursuit_type",
        "risk_flags",
        "title",
        "department",
        "sub_tier",
        "office",
        "posted_date",
        "response_deadline",
        "days_until_deadline",
        "clean_naics",
        "naics_code",
        "classification_code",
        "notice_type",
        "base_type",
        "search_name",
        "search_keyword",
        "search_naics",
        "search_ptype",
        "query_hits",
        "ui_link",
        "score_rationale",
        "description",
    ]

    front_cols = [c for c in front_cols if c in merged.columns]
    remaining = [c for c in merged.columns if c not in front_cols]
    merged = merged[front_cols + remaining]

    merged.to_csv(OUTPUT_CSV, index=False)

    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        merged.to_excel(writer, sheet_name="BD Review", index=False)

        priority = merged[
            merged["recommendation"].isin(
                ["Pursue / Discuss Monday", "Strong Monitor / Validate Owner"]
            )
        ]
        priority.to_excel(writer, sheet_name="Priority Review", index=False)

    print(f"Review tracker saved/updated: {REVIEW_CSV.resolve()}")
    print(f"Merged CSV saved: {OUTPUT_CSV.resolve()}")
    print(f"Merged Excel saved: {OUTPUT_XLSX.resolve()}")
    print(f"Rows merged: {len(merged)}")


if __name__ == "__main__":
    main()