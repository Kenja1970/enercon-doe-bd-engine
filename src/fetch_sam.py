from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# SAM.gov Go/No-Go Scoring
# Target: DOE / NNSA / Federal A/E + Engineering Services
# ============================================================

RAW_DIR = Path("data/raw")
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

INPUT_CSV = RAW_DIR / "sam_active_master.csv"
OUTPUT_CSV = REPORTS_DIR / "sam_go_no_go_ranked.csv"
OUTPUT_XLSX = REPORTS_DIR / "sam_go_no_go_ranked.xlsx"
TOP_20_CSV = REPORTS_DIR / "sam_top_20_review.csv"


# ------------------------------------------------------------
# Target NAICS codes
# ------------------------------------------------------------

TARGET_NAICS = {
    "541330": "Engineering Services",
    "541310": "Architectural Services",
    "541620": "Environmental Consulting Services",
    "541690": "Other Scientific and Technical Consulting Services",
    "541350": "Building Inspection Services",
    "541340": "Drafting Services",
}

# Keep this tight.
# 236220 and 237990 were intentionally removed because they were allowing
# construction-only work into the Top 20 review list.
SECONDARY_NAICS = {
    "541715": "R&D in Nanotechnology / Engineering / Life Sciences",
}

BAD_NAICS_PREFIXES = {
    "31",  # Manufacturing
    "32",  # Manufacturing
    "33",  # Manufacturing
    "42",  # Wholesale trade
    "44",  # Retail
    "45",  # Retail
}


# ------------------------------------------------------------
# High-value positive fit terms
# ------------------------------------------------------------

AE_ENGINEERING_TERMS = [
    "architect engineer",
    "architect-engineer",
    "a-e",
    "ae services",
    "a/e",
    "engineering services",
    "professional engineering",
    "design services",
    "design engineering",
    "engineering design",
    "facility design",
    "title i",
    "title ii",
    "title iii",
    "construction phase services",
    "construction support",
    "construction management",
    "cm services",
    "design-bid-build",
    "design build",
    "design-build",
    "idiq",
    "task order",
    "site investigation",
    "field investigation",
    "engineering assessment",
    "condition assessment",
    "facility assessment",
    "feasibility study",
    "technical study",
    "code analysis",
    "cost estimate",
    "independent technical review",
    "quality assurance",
    "quality control",
]

DOE_SITE_TERMS = [
    "department of energy",
    "doe",
    "energy, department of",
    "nnsa",
    "national nuclear security administration",
    "oak ridge",
    "ornl",
    "y-12",
    "y12",
    "savannah river",
    "srs",
    "hanford",
    "idaho national laboratory",
    "inl",
    "los alamos",
    "lanl",
    "sandia",
    "pantex",
    "wipp",
    "nevada national security site",
    "nnss",
    "kansas city national security campus",
    "kcnsc",
]

DISCIPLINE_TERMS = [
    "mechanical",
    "electrical",
    "civil",
    "structural",
    "architectural",
    "fire protection",
    "plumbing",
    "hvac",
    "instrumentation",
    "controls",
    "i&c",
    "environmental",
    "geotechnical",
    "survey",
    "commissioning",
    "energy",
    "power",
    "nuclear",
    "regulatory",
    "licensing",
    "safety basis",
    "industrial",
    "infrastructure",
    "facility modernization",
    "renovation",
    "remediation",
    "nepa",
    "permitting",
]

EARLY_CAPTURE_TERMS = [
    "sources sought",
    "request for information",
    "rfi",
    "market research",
    "capability statement",
    "industry day",
    "presolicitation",
    "draft request for proposal",
    "draft rfp",
]

SMALL_BUSINESS_TERMS = [
    "small business",
    "small business set-aside",
    "sdvosb",
    "service-disabled veteran",
    "8(a)",
    "8a",
    "hubzone",
    "woman owned",
    "wosb",
    "edwosb",
]


# ------------------------------------------------------------
# Bad-fit / commodity / goods terms
# ------------------------------------------------------------

BAD_FIT_TERMS = [
    "equipment",
    "supplies",
    "supply",
    "parts",
    "replacement parts",
    "spare parts",
    "repair parts",
    "kit",
    "kits",
    "hardware",
    "software license",
    "software subscription",
    "subscription",
    "furniture",
    "chairs",
    "desk",
    "desks",
    "vehicles",
    "vehicle",
    "truck",
    "forklift",
    "trailer",
    "generator",
    "pump",
    "valve",
    "valves",
    "pipe fittings",
    "filters",
    "laboratory supplies",
    "lab supplies",
    "chemical",
    "chemicals",
    "reagent",
    "reagents",
    "protective clothing",
    "ppe",
    "gloves",
    "janitorial",
    "custodial",
    "grounds maintenance",
    "landscaping",
    "cafeteria",
    "food service",
    "security guard",
    "armed guard",
    "medical staffing",
    "temporary staffing",
    "staff augmentation",
    "it help desk",
    "help desk",
    "printer",
    "toner",
    "computers",
    "laptops",
    "servers",
    "network switch",
    "radios",
    "uniforms",
    "crane rental",
    "rental equipment",
    "waste containers",
    "dumpsters",
]

CONSTRUCTION_ONLY_TERMS = [
    "construction only",
    "general construction",
    "roof replacement",
    "paving",
    "asphalt",
    "concrete repair",
    "demolition",
    "install only",
    "installation only",
    "replace",
    "replacement",
    "repair",
    "construction project",
    "contractor shall construct",
    "contractor shall install",
]


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def safe_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).lower()


def hit_terms(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term.lower() in text]


def clean_naics(value: Any) -> str:
    text = safe_text(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[:6]


def parse_date(value: Any) -> pd.Timestamp | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None

    parsed = pd.to_datetime(value, errors="coerce", utc=False)

    if pd.isna(parsed):
        return None

    return parsed


def calculate_days_until_deadline(value: Any) -> int | None:
    deadline = parse_date(value)

    if deadline is None:
        return None

    # SAM.gov dates may be timezone-aware. Convert everything to timezone-naive.
    if getattr(deadline, "tzinfo", None) is not None:
        deadline = deadline.tz_localize(None)

    today = pd.Timestamp.today().normalize()

    if getattr(today, "tzinfo", None) is not None:
        today = today.tz_localize(None)

    return int((deadline.normalize() - today).days)


def classify_recommendation(score: int) -> str:
    if score >= 80:
        return "Pursue / Discuss Monday"
    if score >= 65:
        return "Strong Monitor / Validate Owner"
    if score >= 50:
        return "Monitor / Shape"
    if score >= 35:
        return "Low Priority"
    return "No-Go"


def classify_customer_market(row: pd.Series) -> str:
    text = " ".join(
        [
            safe_text(row.get("full_parent_path_name")),
            safe_text(row.get("department")),
            safe_text(row.get("sub_tier")),
            safe_text(row.get("office")),
            safe_text(row.get("title")),
            safe_text(row.get("description")),
        ]
    )

    if (
        "energy, department of" in text
        or "department of energy" in text
        or "nnsa" in text
        or "national nuclear security administration" in text
    ):
        return "DOE / NNSA"

    if "us army corps of engineers" in text or "u.s. army corps of engineers" in text or "usace" in text:
        return "USACE / Federal Infrastructure"

    if (
        "dept of defense" in text
        or "department of defense" in text
        or "department of the navy" in text
        or "department of the air force" in text
        or "department of the army" in text
    ):
        return "DoD / Defense Infrastructure"

    if "veterans affairs" in text or "department of veterans affairs" in text:
        return "VA / Healthcare Facilities"

    if "general services administration" in text or "public buildings service" in text:
        return "GSA / Federal Buildings"

    if "architect of the capitol" in text:
        return "Federal Buildings / Capitol"

    if "department of homeland security" in text or "dhs" in text:
        return "DHS / Federal Facilities"

    return "Other Federal"


def classify_pursuit_type(row: pd.Series, evidence_text: str) -> str:
    notice_type = safe_text(row.get("notice_type"))
    base_type = safe_text(row.get("base_type"))
    ptype = safe_text(row.get("search_ptype"))

    if ptype == "r" or "sources sought" in evidence_text or "request for information" in evidence_text:
        return "Early Capture / Sources Sought"

    if ptype == "p" or "presolicitation" in evidence_text or "pre-solicitation" in evidence_text:
        return "Pre-Solicitation Watch"

    if ptype == "o" or "solicitation" in notice_type or "solicitation" in base_type:
        return "Active Solicitation"

    if ptype == "k" or "combined synopsis" in evidence_text:
        return "Combined Synopsis / Short-Fuse"

    return "Unclassified"


def assign_drop_reason(
    naics: str,
    bad_hits: list[str],
    construction_hits: list[str],
    ae_hits: list[str],
    eligible_for_action: bool,
) -> str:
    if bad_hits:
        return f"Likely goods/supplies/equipment: {', '.join(bad_hits[:5])}"

    if construction_hits and not ae_hits:
        return f"Likely construction-only without design language: {', '.join(construction_hits[:5])}"

    if naics and naics not in TARGET_NAICS and naics not in SECONDARY_NAICS:
        return f"Suppressed non-target NAICS: {naics}"

    if naics in SECONDARY_NAICS and not ae_hits:
        return f"Adjacent NAICS {naics} but no strong A/E language"

    if not ae_hits:
        return "No strong A/E or engineering-services language"

    if not eligible_for_action:
        return "Suppressed from action review"

    return ""


def assign_action_today(
    score: int,
    customer_market: str,
    pursuit_type: str,
    days_until_deadline: int | None,
    risk_flags: str,
) -> str:
    risk_text = safe_text(risk_flags)

    if "suppressed" in risk_text:
        return "No action - suppressed"

    if "expired" in risk_text or (days_until_deadline is not None and days_until_deadline < 0):
        return "Drop - expired"

    if "goods" in risk_text or "supply" in risk_text:
        return "Drop unless manually confirmed"

    if "construction-only" in risk_text:
        return "No action - construction only"

    if score >= 80 and pursuit_type == "Early Capture / Sources Sought":
        return "Review today - possible shaping opportunity"

    if score >= 80 and pursuit_type == "Active Solicitation":
        return "Review today - confirm owner and deadline"

    if score >= 65 and customer_market in {
        "DOE / NNSA",
        "USACE / Federal Infrastructure",
        "GSA / Federal Buildings",
        "Federal Buildings / Capitol",
    }:
        return "Validate customer owner"

    if score >= 50:
        return "Monitor only"

    return "No action"


def assign_review_priority(score: int, action_today: str) -> str:
    if "Review today" in action_today:
        return "1 - Review Today"
    if "Validate customer owner" in action_today:
        return "2 - Validate Owner"
    if "Monitor only" in action_today or score >= 50:
        return "3 - Monitor"
    if score >= 35:
        return "4 - Low Priority"
    return "5 - Drop"


# ------------------------------------------------------------
# Scoring
# ------------------------------------------------------------

def score_row(row: pd.Series) -> pd.Series:
    title = safe_text(row.get("title"))
    description = safe_text(row.get("description"))
    department = safe_text(row.get("department"))
    sub_tier = safe_text(row.get("sub_tier"))
    office = safe_text(row.get("office"))
    parent = safe_text(row.get("full_parent_path_name"))
    classification_code = safe_text(row.get("classification_code"))

    # IMPORTANT:
    # Do not use search_name, search_keyword, or query_hits to score.
    # They are search trace fields only and can falsely inflate DOE/A-E fit.
    evidence_text = " ".join(
        [
            title,
            description,
            department,
            sub_tier,
            office,
            parent,
            classification_code,
        ]
    )

    score = 0
    reasons = []
    risk_flags = []

    naics = clean_naics(row.get("naics_code"))
    days_until_deadline = calculate_days_until_deadline(row.get("response_deadline"))
    customer_market = classify_customer_market(row)
    pursuit_type = classify_pursuit_type(row, evidence_text)

    ae_hits = hit_terms(evidence_text, AE_ENGINEERING_TERMS)
    site_hits = hit_terms(evidence_text, DOE_SITE_TERMS)
    discipline_hits = hit_terms(evidence_text, DISCIPLINE_TERMS)
    early_hits = hit_terms(evidence_text, EARLY_CAPTURE_TERMS)
    sb_hits = hit_terms(evidence_text, SMALL_BUSINESS_TERMS)
    bad_hits = hit_terms(evidence_text, BAD_FIT_TERMS)
    construction_hits = hit_terms(evidence_text, CONSTRUCTION_ONLY_TERMS)

    # --------------------------------------------------------
    # NAICS fit
    # --------------------------------------------------------

    if naics in TARGET_NAICS:
        score += 35
        reasons.append(f"Target professional services NAICS {naics}: {TARGET_NAICS[naics]}")
    elif naics in SECONDARY_NAICS:
        score += 10
        reasons.append(f"Secondary/adjacent NAICS {naics}: {SECONDARY_NAICS[naics]}")
        risk_flags.append("Adjacent NAICS; verify engineering scope")
    elif any(naics.startswith(prefix) for prefix in BAD_NAICS_PREFIXES):
        score -= 35
        reasons.append(f"Likely goods/manufacturing/retail NAICS: {naics}")
        risk_flags.append("Likely goods/supply opportunity")
    elif naics:
        score -= 25
        reasons.append(f"Non-target NAICS: {naics}")
        risk_flags.append("NAICS does not clearly match A/E services")
    else:
        score -= 10
        reasons.append("Missing NAICS")
        risk_flags.append("Missing NAICS")

    # --------------------------------------------------------
    # A/E and engineering language
    # --------------------------------------------------------

    if ae_hits:
        add = min(30, len(ae_hits) * 8)
        score += add
        reasons.append(f"A/E-engineering language: {', '.join(ae_hits[:5])}")
    else:
        score -= 20
        reasons.append("No strong A/E-engineering language detected")
        risk_flags.append("Scope may not be A/E or engineering services")

    # --------------------------------------------------------
    # DOE / NNSA / site relevance
    # --------------------------------------------------------

    if customer_market == "DOE / NNSA":
        score += 18
        reasons.append("Customer market classified as DOE / NNSA")
    elif site_hits:
        add = min(14, len(site_hits) * 4)
        score += add
        reasons.append(f"DOE/NNSA/site relevance: {', '.join(site_hits[:5])}")
    elif customer_market in {"USACE / Federal Infrastructure", "GSA / Federal Buildings", "Federal Buildings / Capitol"}:
        score += 6
        reasons.append(f"Adjacent federal A/E market: {customer_market}")
    else:
        score -= 5
        reasons.append(f"Non-DOE market classification: {customer_market}")

    # --------------------------------------------------------
    # Discipline fit
    # --------------------------------------------------------

    if discipline_hits:
        add = min(20, len(discipline_hits) * 4)
        score += add
        reasons.append(f"Discipline/capability fit: {', '.join(discipline_hits[:6])}")

    # --------------------------------------------------------
    # Early capture value
    # --------------------------------------------------------

    if early_hits:
        score += 10
        reasons.append(f"Early capture indicator: {', '.join(early_hits[:3])}")

    if pursuit_type == "Early Capture / Sources Sought":
        score += 8
        reasons.append("Sources sought/RFI is useful for shaping")
    elif pursuit_type == "Active Solicitation":
        score += 5
        reasons.append("Active solicitation")
    elif pursuit_type == "Combined Synopsis / Short-Fuse":
        score -= 5
        risk_flags.append("Likely short-fuse combined synopsis")

    # --------------------------------------------------------
    # Small business / teaming relevance
    # --------------------------------------------------------

    if sb_hits:
        score += 4
        reasons.append(f"Small business/team potential: {', '.join(sb_hits[:3])}")
        risk_flags.append("Check set-aside status / prime eligibility")

    # --------------------------------------------------------
    # Bad fit terms
    # --------------------------------------------------------

    if bad_hits:
        penalty = min(70, len(bad_hits) * 15)
        score -= penalty
        reasons.append(f"Bad-fit goods/supply terms: {', '.join(bad_hits[:6])}")
        risk_flags.append("Contains goods/supplies/equipment language")

    if construction_hits:
        construction_penalty = min(35, len(construction_hits) * 10)
        score -= construction_penalty
        reasons.append(f"Construction-only risk terms: {', '.join(construction_hits[:5])}")
        risk_flags.append("May be construction-only rather than A/E services")

    # --------------------------------------------------------
    # Deadline logic
    # --------------------------------------------------------

    if days_until_deadline is None:
        score -= 5
        reasons.append("Missing or unreadable response deadline")
        risk_flags.append("Deadline needs manual verification")
    elif days_until_deadline < 0:
        score -= 50
        reasons.append(f"Expired deadline: {days_until_deadline} days")
        risk_flags.append("Expired")
    elif days_until_deadline <= 3:
        score -= 15
        reasons.append(f"Very short deadline: {days_until_deadline} days")
        risk_flags.append("Short-fuse deadline")
    elif days_until_deadline <= 10:
        score += 3
        reasons.append(f"Near-term deadline: {days_until_deadline} days")
    else:
        score += 8
        reasons.append(f"Workable deadline: {days_until_deadline} days")

    # --------------------------------------------------------
    # Eligibility gate
    # --------------------------------------------------------
    # This suppresses construction-only, commodity, or non-A/E rows from
    # the Top 20 and action tabs. They remain visible in All_Ranked.

    eligible_for_action = True

    if naics not in TARGET_NAICS and naics not in SECONDARY_NAICS:
        eligible_for_action = False
        risk_flags.append("Suppressed: non-target NAICS")
        reasons.append("Suppressed from action review because NAICS is not target or adjacent")

    if naics in SECONDARY_NAICS and not ae_hits:
        eligible_for_action = False
        risk_flags.append("Suppressed: adjacent NAICS without strong A/E language")
        reasons.append("Suppressed because adjacent NAICS lacks strong A/E language")

    if bad_hits:
        eligible_for_action = False
        risk_flags.append("Suppressed: goods/supplies/equipment")
        reasons.append("Suppressed because goods/supplies/equipment terms were detected")

    if construction_hits and not ae_hits:
        eligible_for_action = False
        risk_flags.append("Suppressed: construction-only without design language")
        reasons.append("Suppressed because construction-only terms appear without strong design/A-E language")

    if not eligible_for_action:
        score = min(score, 34)

    # --------------------------------------------------------
    # Final classification
    # --------------------------------------------------------

    score = max(0, min(100, int(score)))

    drop_reason = assign_drop_reason(
        naics=naics,
        bad_hits=bad_hits,
        construction_hits=construction_hits,
        ae_hits=ae_hits,
        eligible_for_action=eligible_for_action,
    )

    risk_flags_text = " | ".join(sorted(set(risk_flags)))

    action_today = assign_action_today(
        score=score,
        customer_market=customer_market,
        pursuit_type=pursuit_type,
        days_until_deadline=days_until_deadline,
        risk_flags=risk_flags_text,
    )

    review_priority = assign_review_priority(score, action_today)

    row["review_priority"] = review_priority
    row["action_today"] = action_today
    row["eligible_for_action"] = eligible_for_action
    row["customer_market"] = customer_market
    row["drop_reason"] = drop_reason
    row["clean_naics"] = naics
    row["days_until_deadline"] = days_until_deadline
    row["pursuit_type"] = pursuit_type
    row["go_no_go_score"] = score
    row["recommendation"] = classify_recommendation(score)
    row["score_rationale"] = " | ".join(reasons)
    row["risk_flags"] = risk_flags_text

    return row


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main() -> None:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_CSV}")

    df = pd.read_csv(INPUT_CSV, dtype=str)

    if df.empty:
        print("Input CSV is empty. Nothing to score.")
        return

    scored = df.apply(score_row, axis=1)

    scored["go_no_go_score"] = pd.to_numeric(scored["go_no_go_score"], errors="coerce").fillna(0)
    scored["days_until_deadline_sort"] = pd.to_numeric(
        scored["days_until_deadline"], errors="coerce"
    ).fillna(9999)

    priority_order = {
        "1 - Review Today": 1,
        "2 - Validate Owner": 2,
        "3 - Monitor": 3,
        "4 - Low Priority": 4,
        "5 - Drop": 5,
    }

    scored["review_priority_sort"] = scored["review_priority"].map(priority_order).fillna(99)

    scored = scored.sort_values(
        by=["review_priority_sort", "go_no_go_score", "days_until_deadline_sort", "posted_date"],
        ascending=[True, False, True, False],
    )

    # Reorder useful columns to the front.
    front_cols = [
        "review_priority",
        "action_today",
        "eligible_for_action",
        "customer_market",
        "go_no_go_score",
        "recommendation",
        "pursuit_type",
        "drop_reason",
        "risk_flags",
        "title",
        "department",
        "sub_tier",
        "office",
        "full_parent_path_name",
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

    existing_front = [c for c in front_cols if c in scored.columns]
    remaining_cols = [c for c in scored.columns if c not in existing_front]
    scored = scored[existing_front + remaining_cols]

    scored.to_csv(OUTPUT_CSV, index=False)

    # Top 20 should be actionable only.
    top20 = scored[
        scored["review_priority"].isin(
            ["1 - Review Today", "2 - Validate Owner", "3 - Monitor"]
        )
        & (scored["eligible_for_action"] == True)
    ].head(20)

    top20.to_csv(TOP_20_CSV, index=False)

    review_today = scored[
        (scored["review_priority"] == "1 - Review Today")
        & (scored["eligible_for_action"] == True)
    ]

    validate_owner = scored[
        (scored["review_priority"] == "2 - Validate Owner")
        & (scored["eligible_for_action"] == True)
    ]

    monitor = scored[
        (scored["review_priority"] == "3 - Monitor")
        & (scored["go_no_go_score"] >= 50)
        & (scored["eligible_for_action"] == True)
    ]

    no_go = scored[
        scored["review_priority"].isin(["4 - Low Priority", "5 - Drop"])
        | scored["risk_flags"].str.contains("Suppressed", case=False, na=False)
        | (scored["eligible_for_action"] != True)
    ]

    doe_nnsa = scored[
        (scored["customer_market"] == "DOE / NNSA")
        & (scored["eligible_for_action"] == True)
    ]

    usace_gsa = scored[
        scored["customer_market"].isin(
            ["USACE / Federal Infrastructure", "GSA / Federal Buildings", "Federal Buildings / Capitol"]
        )
        & (scored["eligible_for_action"] == True)
    ]

    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        review_today.to_excel(writer, sheet_name="1_Review_Today", index=False)
        validate_owner.to_excel(writer, sheet_name="2_Validate_Owner", index=False)
        monitor.to_excel(writer, sheet_name="3_Monitor", index=False)
        no_go.to_excel(writer, sheet_name="4_No_Go", index=False)
        doe_nnsa.to_excel(writer, sheet_name="DOE_NNSA", index=False)
        usace_gsa.to_excel(writer, sheet_name="USACE_GSA", index=False)
        scored.to_excel(writer, sheet_name="All_Ranked", index=False)

    print("\n=== Scoring Complete ===")
    print(f"Input records: {len(df)}")
    print(f"Scored records: {len(scored)}")
    print(f"Review Today: {len(review_today)}")
    print(f"Validate Owner: {len(validate_owner)}")
    print(f"Monitor: {len(monitor)}")
    print(f"No-Go / Suppressed / Low Priority: {len(no_go)}")
    print(f"DOE / NNSA actionable: {len(doe_nnsa)}")
    print(f"USACE / GSA / Federal Buildings actionable: {len(usace_gsa)}")
    print(f"Top 20 actionable saved to: {TOP_20_CSV.resolve()}")
    print(f"CSV saved to: {OUTPUT_CSV.resolve()}")
    print(f"Excel saved to: {OUTPUT_XLSX.resolve()}")


if __name__ == "__main__":
    main()