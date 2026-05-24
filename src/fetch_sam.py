import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv


load_dotenv()

BASE_URL = "https://api.sam.gov/opportunities/v2/search"

RAW_DIR = Path("data/raw")
STATE_DIR = Path("data/state")

MASTER_CSV = RAW_DIR / "sam_active_master.csv"
TODAY_CSV = RAW_DIR / "sam_new_unique_today.csv"
DEBUG_CSV = RAW_DIR / "sam_debug_this_run.csv"
RUN_LOG_CSV = RAW_DIR / "sam_run_log.csv"
STATE_JSON = STATE_DIR / "sam_fetch_state.json"

DEFAULT_LIMIT = 50

COLUMNS = [
    "dedupe_key",
    "notice_id",
    "solicitation_number",
    "title",
    "department",
    "sub_tier",
    "office",
    "posted_date",
    "response_deadline",
    "naics_code",
    "ptype",
    "notice_type",
    "ui_link",
    "description",
    "search_name",
    "search_index",
    "offset_used",
    "fetched_at_utc",
]


# The order matters, but state rotation prevents the first few from being hit every day.
# Keep high-value A/E searches near the top, then rotate through broader DOE/NNSA/site searches.
SEARCH_PLAN: list[dict[str, Any]] = [
    {
        "name": "DOE Engineering Services - Sources Sought",
        "params": {
            "ptype": "r",
            "organizationName": "Department of Energy",
            "ncode": "541330",
        },
    },
    {
        "name": "DOE Engineering Services - Solicitation",
        "params": {
            "ptype": "o",
            "organizationName": "Department of Energy",
            "ncode": "541330",
        },
    },
    {
        "name": "A/E Title Search - Sources Sought",
        "params": {
            "ptype": "r",
            "title": "architect engineer",
            "ncode": "541330",
        },
    },
    {
        "name": "A/E Title Search - Solicitation",
        "params": {
            "ptype": "o",
            "title": "architect engineer",
            "ncode": "541330",
        },
    },
    {
        "name": "NNSA Engineering Services - Sources Sought",
        "params": {
            "ptype": "r",
            "organizationName": "National Nuclear Security Administration",
            "ncode": "541330",
        },
    },
    {
        "name": "NNSA Engineering Services - Solicitation",
        "params": {
            "ptype": "o",
            "organizationName": "National Nuclear Security Administration",
            "ncode": "541330",
        },
    },
    {
        "name": "DOE Architectural Services - Sources Sought",
        "params": {
            "ptype": "r",
            "organizationName": "Department of Energy",
            "ncode": "541310",
        },
    },
    {
        "name": "DOE Architectural Services - Solicitation",
        "params": {
            "ptype": "o",
            "organizationName": "Department of Energy",
            "ncode": "541310",
        },
    },
    {
        "name": "DOE Environmental Consulting - Sources Sought",
        "params": {
            "ptype": "r",
            "organizationName": "Department of Energy",
            "ncode": "541620",
        },
    },
    {
        "name": "DOE Environmental Consulting - Solicitation",
        "params": {
            "ptype": "o",
            "organizationName": "Department of Energy",
            "ncode": "541620",
        },
    },
    {
        "name": "DOE Technical Consulting - Sources Sought",
        "params": {
            "ptype": "r",
            "organizationName": "Department of Energy",
            "ncode": "541690",
        },
    },
    {
        "name": "DOE Technical Consulting - Solicitation",
        "params": {
            "ptype": "o",
            "organizationName": "Department of Energy",
            "ncode": "541690",
        },
    },
    {
        "name": "Oak Ridge Engineering Services",
        "params": {
            "ptype": "r",
            "title": "Oak Ridge engineering services",
            "ncode": "541330",
        },
    },
    {
        "name": "Y-12 Engineering Services",
        "params": {
            "ptype": "r",
            "title": "Y-12 engineering services",
            "ncode": "541330",
        },
    },
    {
        "name": "Savannah River Engineering Services",
        "params": {
            "ptype": "r",
            "title": "Savannah River engineering services",
            "ncode": "541330",
        },
    },
    {
        "name": "Hanford Engineering Services",
        "params": {
            "ptype": "r",
            "title": "Hanford engineering services",
            "ncode": "541330",
        },
    },
    {
        "name": "Idaho National Laboratory Engineering Services",
        "params": {
            "ptype": "r",
            "title": "Idaho National Laboratory engineering services",
            "ncode": "541330",
        },
    },
    {
        "name": "Los Alamos Engineering Services",
        "params": {
            "ptype": "r",
            "title": "Los Alamos engineering services",
            "ncode": "541330",
        },
    },
    {
        "name": "Sandia Engineering Services",
        "params": {
            "ptype": "r",
            "title": "Sandia engineering services",
            "ncode": "541330",
        },
    },
    {
        "name": "Pantex Engineering Services",
        "params": {
            "ptype": "r",
            "title": "Pantex engineering services",
            "ncode": "541330",
        },
    },
    {
        "name": "DOE Fire Protection Engineering",
        "params": {
            "ptype": "r",
            "title": "fire protection engineering",
            "ncode": "541330",
        },
    },
    {
        "name": "DOE Facility Modernization Engineering",
        "params": {
            "ptype": "r",
            "title": "facility modernization engineering",
            "ncode": "541330",
        },
    },
    {
        "name": "DOE Mechanical Engineering",
        "params": {
            "ptype": "r",
            "title": "mechanical engineering",
            "ncode": "541330",
        },
    },
    {
        "name": "DOE Electrical Engineering",
        "params": {
            "ptype": "r",
            "title": "electrical engineering",
            "ncode": "541330",
        },
    },
    {
        "name": "DOE Civil Structural Engineering",
        "params": {
            "ptype": "r",
            "title": "civil structural engineering",
            "ncode": "541330",
        },
    },
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def date_range(days_back: int) -> tuple[str, str]:
    today = datetime.now()
    start = today - timedelta(days=days_back)
    return start.strftime("%m/%d/%Y"), today.strftime("%m/%d/%Y")


def load_state() -> dict[str, Any]:
    if STATE_JSON.exists():
        try:
            with STATE_JSON.open("r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
    else:
        state = {}

    state.setdefault("next_query_index", 0)
    state.setdefault("query_offsets", {})
    state.setdefault("query_stats", {})
    state.setdefault("last_run_utc", None)
    state.setdefault("total_runs", 0)

    # Defensive cleanup if search plan changed.
    if not isinstance(state["next_query_index"], int):
        state["next_query_index"] = 0

    if state["next_query_index"] >= len(SEARCH_PLAN):
        state["next_query_index"] = 0

    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")


def safe_get(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return str(value)
    return ""


def extract_opportunities(payload: dict[str, Any]) -> list[dict[str, Any]]:
    # SAM.gov commonly returns opportunitiesData, but keep this defensive.
    for key in ["opportunitiesData", "data", "records", "opportunities"]:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def make_dedupe_key(row: dict[str, str]) -> str:
    if row.get("notice_id"):
        return f"notice:{row['notice_id']}".lower()

    if row.get("solicitation_number"):
        return f"sol:{row['solicitation_number']}".lower()

    title = row.get("title", "").strip().lower()
    deadline = row.get("response_deadline", "").strip().lower()
    office = row.get("office", "").strip().lower()
    return f"title:{title}|deadline:{deadline}|office:{office}"


def normalize_record(
    record: dict[str, Any],
    *,
    search_name: str,
    search_index: int,
    offset_used: int,
) -> dict[str, str]:
    title = safe_get(record, "title")
    notice_id = safe_get(record, "noticeId", "notice_id", "_id")
    solicitation_number = safe_get(record, "solicitationNumber", "solicitation_number")
    department = safe_get(record, "department", "departmentName", "fullParentPathName")
    sub_tier = safe_get(record, "subTier", "subTierName")
    office = safe_get(record, "office", "officeName")
    posted_date = safe_get(record, "postedDate", "posted_date")
    response_deadline = safe_get(record, "responseDeadLine", "responseDeadline", "response_deadline")
    naics_code = safe_get(record, "naicsCode", "naics_code", "ncode")
    ptype = safe_get(record, "type", "ptype")
    notice_type = safe_get(record, "baseType", "noticeType")
    ui_link = safe_get(record, "uiLink", "ui_link", "url")
    description = safe_get(record, "description", "shortDescription")

    row = {
        "dedupe_key": "",
        "notice_id": notice_id,
        "solicitation_number": solicitation_number,
        "title": title,
        "department": department,
        "sub_tier": sub_tier,
        "office": office,
        "posted_date": posted_date,
        "response_deadline": response_deadline,
        "naics_code": naics_code,
        "ptype": ptype,
        "notice_type": notice_type,
        "ui_link": ui_link,
        "description": description,
        "search_name": search_name,
        "search_index": str(search_index),
        "offset_used": str(offset_used),
        "fetched_at_utc": utc_now_iso(),
    }

    row["dedupe_key"] = make_dedupe_key(row)
    return row


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if df.empty:
        df = pd.DataFrame(columns=COLUMNS)

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[COLUMNS]
    df.to_csv(path, index=False)

    print(f"Saved CSV: {path.resolve()} | rows={len(df)} | bytes={path.stat().st_size}")


def load_master() -> pd.DataFrame:
    if not MASTER_CSV.exists():
        return pd.DataFrame(columns=COLUMNS)

    try:
        df = pd.read_csv(MASTER_CSV, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=COLUMNS)

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""

    if "dedupe_key" not in df.columns or df["dedupe_key"].eq("").all():
        df["dedupe_key"] = df.apply(lambda r: make_dedupe_key(r.to_dict()), axis=1)

    return df[COLUMNS]


def append_run_log(entry: dict[str, Any]) -> None:
    if RUN_LOG_CSV.exists():
        try:
            old = pd.read_csv(RUN_LOG_CSV, dtype=str).fillna("")
        except Exception:
            old = pd.DataFrame()
    else:
        old = pd.DataFrame()

    new = pd.DataFrame([entry])
    combined = pd.concat([old, new], ignore_index=True)
    combined.to_csv(RUN_LOG_CSV, index=False)
    print(f"Saved CSV: {RUN_LOG_CSV.resolve()} | rows={len(combined)} | bytes={RUN_LOG_CSV.stat().st_size}")


def call_sam(api_key: str, params: dict[str, Any]) -> tuple[list[dict[str, Any]], bool, str]:
    request_params = dict(params)
    request_params["api_key"] = api_key

    printable = {k: v for k, v in params.items()}
    print(f"SAM request: {printable}")

    try:
        response = requests.get(BASE_URL, params=request_params, timeout=60)
    except requests.RequestException as exc:
        return [], True, f"SAM.gov request exception: {exc}"

    if response.status_code == 429:
        return [], True, f"SAM.gov throttle/server issue: HTTP 429: {response.text}"

    if response.status_code >= 500:
        return [], True, f"SAM.gov throttle/server issue: HTTP {response.status_code}: {response.text}"

    if response.status_code != 200:
        return [], False, f"SAM.gov request failed: HTTP {response.status_code}: {response.text}"

    try:
        payload = response.json()
    except Exception as exc:
        return [], False, f"SAM.gov JSON parse failure: {exc}; body={response.text[:500]}"

    records = extract_opportunities(payload)
    return records, False, ""


def advance_query_index(current_index: int) -> int:
    next_index = current_index + 1
    if next_index >= len(SEARCH_PLAN):
        next_index = 0
    return next_index


def fetch_statefully(
    *,
    api_key: str,
    days_back: int,
    limit: int,
    max_calls: int,
    sleep_seconds: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    posted_from, posted_to = date_range(days_back)
    state = load_state()

    all_rows: list[dict[str, str]] = []
    calls_made = 0
    records_returned = 0
    quota_stop = False
    messages: list[str] = []
    searches_run: list[str] = []

    query_index = int(state.get("next_query_index", 0))

    for _ in range(max_calls):
        plan = SEARCH_PLAN[query_index]
        search_name = plan["name"]
        search_key = str(query_index)

        offset = int(state.get("query_offsets", {}).get(search_key, 0))

        params = {
            "postedFrom": posted_from,
            "postedTo": posted_to,
            "limit": str(limit),
            "offset": str(offset),
        }
        params.update(plan["params"])

        records, is_quota_or_server, message = call_sam(api_key, params)

        if is_quota_or_server:
            quota_stop = True
            messages.append(message)
            print(f"Stopped on SAM.gov quota/throttle/server issue: {message}")
            break

        if message:
            messages.append(message)
            print(message)

        calls_made += 1
        records_returned += len(records)
        searches_run.append(search_name)

        for record in records:
            all_rows.append(
                normalize_record(
                    record,
                    search_name=search_name,
                    search_index=query_index,
                    offset_used=offset,
                )
            )

        stats = state.setdefault("query_stats", {}).setdefault(search_key, {})
        stats["name"] = search_name
        stats["last_checked_utc"] = utc_now_iso()
        stats["last_offset_used"] = offset
        stats["last_records_returned"] = len(records)

        # Pagination and rotation logic:
        # - If the query returned a full page, continue this same query next time at the next offset.
        # - If it returned less than a full page, assume this query is exhausted for now and rotate.
        if len(records) >= limit:
            state["query_offsets"][search_key] = offset + limit
            state["next_query_index"] = query_index
        else:
            state["query_offsets"][search_key] = 0
            query_index = advance_query_index(query_index)
            state["next_query_index"] = query_index

        save_state(state)

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    state["last_run_utc"] = utc_now_iso()
    state["total_runs"] = int(state.get("total_runs", 0)) + 1
    save_state(state)

    debug_df = pd.DataFrame(all_rows, columns=COLUMNS)

    run_summary = {
        "run_at_utc": utc_now_iso(),
        "calls_made": calls_made,
        "records_returned_this_run": records_returned,
        "new_unique_active_this_run": None,
        "master_active_unique_records": None,
        "quota_throttle_stop": quota_stop,
        "next_query_index": state.get("next_query_index"),
        "searches": " | ".join(searches_run),
        "messages": " | ".join(messages),
    }

    return debug_df, run_summary


def merge_with_master(debug_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    master_before = load_master()
    before_keys = set(master_before["dedupe_key"].astype(str).tolist())

    if debug_df.empty:
        master_after = master_before.copy()
        new_today = pd.DataFrame(columns=COLUMNS)
        return master_after, new_today

    for col in COLUMNS:
        if col not in debug_df.columns:
            debug_df[col] = ""

    debug_df = debug_df[COLUMNS].fillna("")
    debug_df = debug_df[debug_df["dedupe_key"].astype(str).str.len() > 0]

    new_today = debug_df[~debug_df["dedupe_key"].isin(before_keys)].copy()

    combined = pd.concat([master_before, debug_df], ignore_index=True).fillna("")
    combined = combined.drop_duplicates(subset=["dedupe_key"], keep="last")
    combined = combined[COLUMNS]

    return combined, new_today[COLUMNS] if not new_today.empty else pd.DataFrame(columns=COLUMNS)


def print_state_summary() -> None:
    state = load_state()
    next_index = int(state.get("next_query_index", 0))
    next_name = SEARCH_PLAN[next_index]["name"] if SEARCH_PLAN else "None"

    print("")
    print("=== Stateful Coverage Status ===")
    print(f"Next query index: {next_index}")
    print(f"Next query name: {next_name}")
    print(f"State file: {STATE_JSON.resolve()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch SAM.gov opportunities with stateful rotation and pagination.")
    parser.add_argument("--max-calls", type=int, default=5, help="Maximum SAM.gov API calls to make this run.")
    parser.add_argument("--days-back", type=int, default=45, help="Lookback window for postedFrom.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="SAM.gov page size.")
    parser.add_argument("--sleep-seconds", type=float, default=1.0, help="Delay between API calls.")
    parser.add_argument("--reset-state", action="store_true", help="Reset query rotation and offsets before running.")
    parser.add_argument("--show-state", action="store_true", help="Show current state and exit.")
    return parser.parse_args()


def main() -> None:
    ensure_dirs()
    args = parse_args()

    if args.reset_state and STATE_JSON.exists():
        STATE_JSON.unlink()
        print(f"Deleted state file: {STATE_JSON.resolve()}")

    if args.show_state:
        print_state_summary()
        return

    api_key = os.getenv("SAM_API_KEY", "").strip()
    if not api_key:
        print("ERROR: SAM_API_KEY is not set. Add it to .env locally or Cloud Run secrets.", file=sys.stderr)
        sys.exit(1)

    debug_df, run_summary = fetch_statefully(
        api_key=api_key,
        days_back=args.days_back,
        limit=args.limit,
        max_calls=args.max_calls,
        sleep_seconds=args.sleep_seconds,
    )

    master_after, new_today = merge_with_master(debug_df)

    run_summary["new_unique_active_this_run"] = len(new_today)
    run_summary["master_active_unique_records"] = len(master_after)

    save_csv(debug_df, DEBUG_CSV)
    save_csv(master_after, MASTER_CSV)
    save_csv(new_today, TODAY_CSV)
    append_run_log(run_summary)

    print("")
    print("=== Fetch Complete ===")
    print(f"Calls made: {run_summary['calls_made']}")
    print(f"Records returned: {run_summary['records_returned_this_run']}")
    print(f"Master active unique records: {run_summary['master_active_unique_records']}")
    print(f"New unique active this run: {run_summary['new_unique_active_this_run']}")
    print(f"Quota/throttle stop: {run_summary['quota_throttle_stop']}")
    print_state_summary()


if __name__ == "__main__":
    main()