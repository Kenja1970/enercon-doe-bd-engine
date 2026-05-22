from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.sam.gov/opportunities/v2/search"

RAW_DIR = Path("data/raw")
CACHE_DIR = Path("data/cache")
STATE_DIR = Path("data/state")
REPORTS_DIR = Path("reports")

MASTER_CSV = RAW_DIR / "sam_active_master.csv"
NEW_TODAY_CSV = RAW_DIR / "sam_new_unique_today.csv"
DEBUG_CSV = RAW_DIR / "sam_debug_this_run.csv"
RAW_JSON = RAW_DIR / "sam_raw_latest.json"
RUN_LOG_CSV = RAW_DIR / "sam_run_log.csv"
STATE_JSON = STATE_DIR / "sam_query_state.json"

for directory in [RAW_DIR, CACHE_DIR, STATE_DIR, REPORTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# SAM.gov official params used here:
# - postedFrom / postedTo are mandatory with date format MM/dd/yyyy
# - ptype is procurement type: r = Sources Sought, o = Solicitation, p = Presolicitation, k = Combined Synopsis/Solicitation
# - ncode is NAICS code, not naicsCode
# - title is title search
# - organizationName filters by department/subtier/office name and supports general search
SEARCH_PLAN = [
    {"name": "DOE Engineering Sources Sought", "organizationName": "Department of Energy", "ncode": "541330", "ptype": "r"},
    {"name": "DOE Engineering Solicitations", "organizationName": "Department of Energy", "ncode": "541330", "ptype": "o"},
    {"name": "DOE A-E Sources Sought", "title": "architect engineer", "ncode": "541330", "ptype": "r"},
    {"name": "DOE A-E Solicitations", "title": "architect engineer", "ncode": "541330", "ptype": "o"},
    {"name": "NNSA Engineering Sources Sought", "organizationName": "National Nuclear Security Administration", "ncode": "541330", "ptype": "r"},
    {"name": "NNSA Engineering Solicitations", "organizationName": "National Nuclear Security Administration", "ncode": "541330", "ptype": "o"},
    {"name": "DOE Architectural Sources Sought", "organizationName": "Department of Energy", "ncode": "541310", "ptype": "r"},
    {"name": "DOE Architectural Solicitations", "organizationName": "Department of Energy", "ncode": "541310", "ptype": "o"},
    {"name": "DOE Environmental Consulting Sources Sought", "organizationName": "Department of Energy", "ncode": "541620", "ptype": "r"},
    {"name": "DOE Environmental Consulting Solicitations", "organizationName": "Department of Energy", "ncode": "541620", "ptype": "o"},
    {"name": "DOE Technical Consulting Sources Sought", "organizationName": "Department of Energy", "ncode": "541690", "ptype": "r"},
    {"name": "DOE Technical Consulting Solicitations", "organizationName": "Department of Energy", "ncode": "541690", "ptype": "o"},
    {"name": "Oak Ridge Engineering", "organizationName": "Oak Ridge", "ncode": "541330", "ptype": "r"},
    {"name": "Y-12 Engineering", "organizationName": "Y-12", "ncode": "541330", "ptype": "r"},
    {"name": "Savannah River Engineering", "organizationName": "Savannah River", "ncode": "541330", "ptype": "r"},
    {"name": "Hanford Engineering", "organizationName": "Hanford", "ncode": "541330", "ptype": "r"},
    {"name": "INL Engineering", "organizationName": "Idaho National Laboratory", "ncode": "541330", "ptype": "r"},
    {"name": "Los Alamos Engineering", "organizationName": "Los Alamos", "ncode": "541330", "ptype": "r"},
    {"name": "Sandia Engineering", "organizationName": "Sandia", "ncode": "541330", "ptype": "r"},
    {"name": "Pantex Engineering", "organizationName": "Pantex", "ncode": "541330", "ptype": "r"},
    {"name": "Fire Protection Engineering", "title": "fire protection engineering", "ncode": "541330", "ptype": "r"},
    {"name": "Facility Modernization Engineering", "title": "facility modernization engineering", "ncode": "541330", "ptype": "r"},
    {"name": "Mechanical Engineering", "title": "mechanical engineering", "ncode": "541330", "ptype": "r"},
    {"name": "Electrical Engineering", "title": "electrical engineering", "ncode": "541330", "ptype": "r"},
    {"name": "Civil Structural Engineering", "title": "civil structural engineering", "ncode": "541330", "ptype": "r"},
]

COLUMNS = [
    "notice_id", "title", "solicitation_number", "posted_date", "response_deadline",
    "active", "notice_type", "base_type", "archive_type", "archive_date", "set_aside",
    "set_aside_code", "naics_code", "classification_code", "department", "sub_tier",
    "office", "full_parent_path_name", "organization_type", "description", "ui_link",
    "resource_links", "point_of_contact", "place_of_performance", "office_address",
    "search_name", "search_title", "search_organization", "search_naics", "search_ptype",
    "first_seen", "last_seen", "query_hits",
]


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def today_mmddyyyy() -> str:
    return datetime.now().strftime("%m/%d/%Y")


def days_back_mmddyyyy(days_back: int) -> str:
    return (datetime.now() - timedelta(days=days_back)).strftime("%m/%d/%Y")


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value)


def clean_nan(value: Any) -> str:
    text = safe_str(value)
    return "" if text.lower() == "nan" else text


def cache_key(params: dict[str, Any]) -> str:
    safe_params = {k: v for k, v in params.items() if k != "api_key"}
    raw = json.dumps(safe_params, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def load_state() -> dict[str, Any]:
    if STATE_JSON.exists():
        try:
            return json.loads(STATE_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {"completed_searches": []}
    return {"completed_searches": []}


def save_state(state: dict[str, Any]) -> None:
    STATE_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_next_searches(reset_stack: bool = False) -> list[dict[str, str]]:
    if reset_stack:
        state = {"completed_searches": []}
        save_state(state)
    else:
        state = load_state()

    completed = set(state.get("completed_searches", []))
    remaining = [s for s in SEARCH_PLAN if s["name"] not in completed]

    if not remaining:
        state = {"completed_searches": []}
        save_state(state)
        return SEARCH_PLAN.copy()

    return remaining


def mark_search_complete(search_name: str) -> None:
    state = load_state()
    completed = set(state.get("completed_searches", []))
    completed.add(search_name)
    state["completed_searches"] = sorted(completed)
    state["last_updated"] = now_iso()
    save_state(state)


def build_params(search: dict[str, str], api_key: str, days_back: int, limit: int, offset: int) -> dict[str, Any]:
    params: dict[str, Any] = {
        "api_key": api_key,
        "postedFrom": days_back_mmddyyyy(days_back),
        "postedTo": today_mmddyyyy(),
        "limit": str(limit),
        "offset": str(offset),
    }

    for key in ["ptype", "title", "organizationName", "ncode", "ccode", "state", "typeOfSetAside"]:
        if search.get(key):
            params[key] = search[key]

    return params


def fetch_one_page(search: dict[str, str], api_key: str, days_back: int, limit: int, offset: int, use_cache: bool) -> tuple[dict[str, Any], bool]:
    params = build_params(search, api_key, days_back, limit, offset)
    ck = cache_key(params)
    cache_file = CACHE_DIR / f"sam_{ck}.json"

    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8")), True

    safe_params = {k: v for k, v in params.items() if k != "api_key"}
    print(f"SAM request: {safe_params}")

    response = requests.get(BASE_URL, params=params, timeout=60)

    if response.status_code in {429, 500, 502, 503, 504}:
        raise RuntimeError(f"SAM.gov throttle/server issue: HTTP {response.status_code}: {response.text[:500]}")

    if response.status_code == 404:
        data = {"totalRecords": 0, "opportunitiesData": []}
        cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data, False

    response.raise_for_status()
    data = response.json()
    cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data, False


def record_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("opportunitiesData")
    if isinstance(records, list):
        return records
    data = payload.get("data")
    if isinstance(data, list):
        return data
    return []


def normalize_record(record: dict[str, Any], search: dict[str, str]) -> dict[str, Any]:
    notice_id = record.get("noticeId") or record.get("noticeid") or record.get("notice_id") or ""

    poc = record.get("pointOfContact") or record.get("pointofContact") or ""
    pop = record.get("placeOfPerformance") or ""
    office_address = record.get("officeAddress") or ""
    resource_links = record.get("resourceLinks") or ""

    return {
        "notice_id": clean_nan(notice_id),
        "title": clean_nan(record.get("title")),
        "solicitation_number": clean_nan(record.get("solicitationNumber")),
        "posted_date": clean_nan(record.get("postedDate")),
        "response_deadline": clean_nan(record.get("responseDeadLine") or record.get("reponseDeadLine")),
        "active": clean_nan(record.get("active")),
        "notice_type": clean_nan(record.get("type")),
        "base_type": clean_nan(record.get("baseType")),
        "archive_type": clean_nan(record.get("archiveType")),
        "archive_date": clean_nan(record.get("archiveDate")),
        "set_aside": clean_nan(record.get("typeOfSetAsideDescription") or record.get("setAside")),
        "set_aside_code": clean_nan(record.get("typeOfSetAside") or record.get("setAsideCode")),
        "naics_code": clean_nan(record.get("naicsCode")),
        "classification_code": clean_nan(record.get("classificationCode")),
        "department": clean_nan(record.get("department")),
        "sub_tier": clean_nan(record.get("subtier")),
        "office": clean_nan(record.get("office")),
        "full_parent_path_name": clean_nan(record.get("fullParentPathName")),
        "organization_type": clean_nan(record.get("organizationType")),
        "description": clean_nan(record.get("description")),
        "ui_link": clean_nan(record.get("uiLink")),
        "resource_links": json.dumps(resource_links) if isinstance(resource_links, (list, dict)) else clean_nan(resource_links),
        "point_of_contact": json.dumps(poc) if isinstance(poc, (list, dict)) else clean_nan(poc),
        "place_of_performance": json.dumps(pop) if isinstance(pop, (list, dict)) else clean_nan(pop),
        "office_address": json.dumps(office_address) if isinstance(office_address, (list, dict)) else clean_nan(office_address),
        "search_name": search.get("name", ""),
        "search_title": search.get("title", ""),
        "search_organization": search.get("organizationName", ""),
        "search_naics": search.get("ncode", ""),
        "search_ptype": search.get("ptype", ""),
        "first_seen": now_iso(),
        "last_seen": now_iso(),
        "query_hits": search.get("name", ""),
    }


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[COLUMNS]


def load_master() -> pd.DataFrame:
    if MASTER_CSV.exists():
        try:
            return ensure_columns(pd.read_csv(MASTER_CSV, dtype=str).fillna(""))
        except Exception:
            return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame(columns=COLUMNS)


def is_active_value(value: Any) -> bool:
    text = safe_str(value).strip().lower()
    return text in {"yes", "true", "active", "1", ""}


def merge_master(master: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    master = ensure_columns(master.copy()).fillna("")
    new_df = ensure_columns(new_df.copy()).fillna("")

    if new_df.empty:
        return master

    combined = pd.concat([master, new_df], ignore_index=True)
    combined["notice_id"] = combined["notice_id"].astype(str).str.strip()
    combined = combined[combined["notice_id"] != ""]

    combined["_is_new"] = combined.index >= len(master)
    combined = combined.sort_values(["notice_id", "_is_new"], ascending=[True, True])

    merged_rows: list[dict[str, Any]] = []
    for notice_id, group in combined.groupby("notice_id", dropna=False):
        rows = group.to_dict("records")
        base = rows[-1].copy()
        first_seen_values = [r.get("first_seen", "") for r in rows if r.get("first_seen")]
        base["first_seen"] = min(first_seen_values) if first_seen_values else now_iso()
        base["last_seen"] = now_iso()

        hits = []
        for r in rows:
            for field in ["query_hits", "search_name"]:
                value = clean_nan(r.get(field, ""))
                if value and value not in hits:
                    hits.append(value)
        base["query_hits"] = " | ".join(hits)
        merged_rows.append(base)

    merged = pd.DataFrame(merged_rows)
    merged = ensure_columns(merged).fillna("")
    merged = merged[merged["active"].apply(is_active_value)]
    return merged.sort_values(["posted_date", "title"], ascending=[False, True])


def write_csv_checked(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Saved CSV: {path.resolve()} | rows={len(df)} | bytes={path.stat().st_size}")


def append_run_log(row: dict[str, Any]) -> None:
    log_df = pd.DataFrame([row])
    if RUN_LOG_CSV.exists():
        old = pd.read_csv(RUN_LOG_CSV, dtype=str)
        log_df = pd.concat([old, log_df], ignore_index=True)
    write_csv_checked(log_df, RUN_LOG_CSV)


def build_single_search(args: argparse.Namespace) -> dict[str, str]:
    search = {"name": "Manual Search"}
    if args.query:
        # Use title for literal opportunity title search. Also supports organizationName through --organization.
        search["title"] = args.query
        search["name"] = f"Manual: {args.query}"
    if args.organization:
        search["organizationName"] = args.organization
        search["name"] = f"Manual Org: {args.organization}"
    if args.naics:
        search["ncode"] = args.naics
    if args.ptype:
        search["ptype"] = args.ptype
    return search


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch SAM.gov A/E opportunities and maintain active master CSV.")
    parser.add_argument("--max-calls", type=int, default=1)
    parser.add_argument("--days-back", type=int, default=45)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--reset-stack", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--query", default="", help="Manual title search term.")
    parser.add_argument("--organization", default="", help="Manual organizationName search term.")
    parser.add_argument("--naics", default="", help="Manual NAICS filter. Sent to SAM.gov as ncode.")
    parser.add_argument("--ptype", default="", help="Manual ptype filter, e.g. r, o, p, k.")
    args = parser.parse_args()

    api_key = os.getenv("SAM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SAM_API_KEY is not configured.")

    use_cache = not args.no_cache
    calls_made = 0
    records_returned = 0
    all_records: list[dict[str, Any]] = []
    searches_run: list[str] = []
    quota_or_throttle = False

    searches = [build_single_search(args)] if (args.query or args.organization or args.naics or args.ptype) else get_next_searches(args.reset_stack)

    for search in searches:
        if calls_made >= args.max_calls:
            break

        try:
            payload, cache_hit = fetch_one_page(
                search=search,
                api_key=api_key,
                days_back=args.days_back,
                limit=args.limit,
                offset=args.offset,
                use_cache=use_cache,
            )
            if not cache_hit:
                calls_made += 1
                time.sleep(1)

            records = record_list(payload)
            records_returned += len(records)
            searches_run.append(search.get("name", ""))
            all_records.extend([normalize_record(r, search) for r in records])

            if not (args.query or args.organization or args.naics or args.ptype):
                mark_search_complete(search["name"])

            RAW_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        except RuntimeError as exc:
            quota_or_throttle = True
            print(f"Stopped on SAM.gov quota/throttle/server issue: {exc}")
            break

    new_df = ensure_columns(pd.DataFrame(all_records)) if all_records else pd.DataFrame(columns=COLUMNS)
    new_df = new_df.drop_duplicates(subset=["notice_id"], keep="last") if not new_df.empty else new_df

    master_before = load_master()
    before_ids = set(master_before["notice_id"].dropna().astype(str)) if not master_before.empty else set()
    master_after = merge_master(master_before, new_df)
    after_new = master_after[~master_after["notice_id"].astype(str).isin(before_ids)].copy() if not master_after.empty else pd.DataFrame(columns=COLUMNS)

    write_csv_checked(new_df, DEBUG_CSV)
    write_csv_checked(master_after, MASTER_CSV)
    write_csv_checked(after_new, NEW_TODAY_CSV)

    append_run_log({
        "run_at": now_iso(),
        "calls_made": calls_made,
        "records_returned_this_run": records_returned,
        "new_unique_active_this_run": len(after_new),
        "master_active_unique_records": len(master_after),
        "quota_or_throttle": quota_or_throttle,
        "searches": " | ".join(searches_run),
    })

    print("\n=== Fetch Complete ===")
    print(f"Calls made: {calls_made}")
    print(f"Records returned: {records_returned}")
    print(f"Master active unique records: {len(master_after)}")
    print(f"New unique active this run: {len(after_new)}")
    print(f"Quota/throttle stop: {quota_or_throttle}")


if __name__ == "__main__":
    main()
