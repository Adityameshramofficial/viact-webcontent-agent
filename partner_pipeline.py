"""
partner_pipeline.py — Agent 11 orchestrator.

3-agent pipeline:
  Agent 1: Auto-discover new competitors → Competitors tab
  Agent 2: Discover partners for one/all competitors → competitor tabs
  Agent 3: Enrich contact info (email cascade) — runs inside Agent 2

Usage:
    python partner_pipeline.py --list
    python partner_pipeline.py --discover-competitors
    python partner_pipeline.py --competitor openspace
    python partner_pipeline.py --all
    python partner_pipeline.py --all-agents

Workflow doc: workflows/partner_outreach.md
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

from discover_partners import COMPETITOR_MAP, discover_partners
from push_to_sheets import push_partners, push_competitors, read_tracked_competitors


def log(msg: str):
    print(f"[partner] {msg}", flush=True)


# ── Agent 1 wrapper ───────────────────────────────────────────────────────────

def run_agent1() -> int:
    """Auto-discover new competitors. Returns count of new competitors added."""
    from discover_competitors import discover_competitors

    log("=== Agent 1: Competitor Discovery ===")
    try:
        new_comps = discover_competitors(progress=lambda m: log(f"  {m}"))
    except Exception as e:
        log(f"  Agent 1 FAILED: {e}")
        return 0

    if not new_comps:
        log("  No new competitors found this run.")
        return 0

    try:
        appended = push_competitors(new_comps)
        log(f"  Competitors tab: {appended} new row(s) added")
        return appended
    except Exception as e:
        log(f"  Push failed: {e}")
        return 0


# ── Agent 2+3 wrapper for one competitor ──────────────────────────────────────

def run_one(slug: str, name_override: str = "", domain_override: str = "",
            tab_override: str = "") -> dict:
    """
    Discover + enrich + push for a single competitor.

    Args:
        slug: COMPETITOR_MAP key, OR a tracked-competitor identifier.
        name_override / domain_override: For ad-hoc competitors not in the map
            (from the Competitors tab).
        tab_override: Explicit tab name to write to. Defaults to slug's tab
            in COMPETITOR_MAP, or `name_override` for ad-hoc.

    Returns:
        {slug, discovered, appended, error}
    """
    if slug in COMPETITOR_MAP:
        comp = COMPETITOR_MAP[slug]
        display_name = comp["name"]
        tab = tab_override or comp["tab"]
    else:
        display_name = name_override or slug
        tab = tab_override or name_override or slug

    log(f"=== {display_name} — tab: '{tab}' ===")
    try:
        rows = discover_partners(
            slug,
            progress=lambda m: log(f"  {m}"),
            name_override=name_override,
            domain_override=domain_override,
        )
    except Exception as e:
        log(f"  DISCOVERY FAILED: {e}")
        return {"slug": slug, "discovered": 0, "appended": 0, "error": str(e)}

    if not rows:
        log("  No partners discovered.")
        return {"slug": slug, "discovered": 0, "appended": 0, "error": None}

    try:
        appended = push_partners(tab, rows)
        log(f"  Sheet: {appended} new row(s) appended (of {len(rows)} discovered)")
        return {"slug": slug, "discovered": len(rows), "appended": appended, "error": None}
    except Exception as e:
        log(f"  SHEET PUSH FAILED: {e}")
        return {"slug": slug, "discovered": len(rows), "appended": 0, "error": str(e)}


# ── Utilities ─────────────────────────────────────────────────────────────────

def _domain_from_website(website: str) -> str:
    """Extract bare domain: 'https://www.openspace.ai/' → 'openspace.ai'."""
    import re
    if not website:
        return ""
    w = website.lower().strip()
    w = re.sub(r"^https?://", "", w)
    w = re.sub(r"^www\.", "", w)
    return w.split("/")[0].strip()


def _print_summary(summary: list[dict], label: str):
    log(f"=== {label} ===")
    total_disc = sum(s["discovered"] for s in summary)
    total_app = sum(s["appended"] for s in summary)
    failed = [s for s in summary if s["error"]]
    log(f"  Discovered: {total_disc} partners across {len(summary)} competitor(s)")
    log(f"  Appended:   {total_app} new rows to sheets")
    if failed:
        log(f"  Failures:   {len(failed)} — {', '.join(s['slug'] for s in failed)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Agent 11 — Partner Discovery Pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true",
                       help="Print the competitor map and exit")
    group.add_argument("--discover-competitors", action="store_true",
                       help="Agent 1 only — find new competitors, push to Competitors tab")
    group.add_argument("--competitor",
                       help=f"Agent 2+3 for one competitor. Slugs: {', '.join(COMPETITOR_MAP.keys())}")
    group.add_argument("--all", action="store_true",
                       help="Agent 2+3 for ALL competitors in COMPETITOR_MAP")
    group.add_argument("--all-agents", action="store_true",
                       help="Full chain: Agent 1 → Agent 2+3 for hardcoded + all Track-status tracked competitors")
    group.add_argument("--daily", action="store_true",
                       help="Daily cron mode: pick ONE competitor (rotated by today's date) from "
                            "Competitors tab (Status=Track). On Mondays, also runs Agent 1.")
    args = parser.parse_args()

    # ── --list ────────────────────────────────────────────────────────────────
    if args.list:
        for slug, c in COMPETITOR_MAP.items():
            print(f"  {slug:14} → {c['name']:14} ({c['domain']}) → tab '{c['tab']}'")
        return

    # ── Sanity check ──────────────────────────────────────────────────────────
    if not os.getenv("PARTNER_SHEET_ID"):
        log("ERROR: PARTNER_SHEET_ID not set in .env")
        log("  Add: PARTNER_SHEET_ID=1Q2XJZ2STaCN94DK4JEnS1mHkrgILfFljjNCc1dy_5qw")
        sys.exit(1)

    # ── --discover-competitors ────────────────────────────────────────────────
    if args.discover_competitors:
        run_agent1()
        return

    # ── --competitor ──────────────────────────────────────────────────────────
    if args.competitor:
        if args.competitor not in COMPETITOR_MAP:
            log(f"ERROR: unknown competitor '{args.competitor}'. Use --list.")
            sys.exit(1)
        run_one(args.competitor)
        return

    # ── --all ─────────────────────────────────────────────────────────────────
    if args.all:
        summary = []
        for slug in COMPETITOR_MAP:
            summary.append(run_one(slug))
            time.sleep(2)  # gentle pacing
        _print_summary(summary, "Summary — all hardcoded competitors")
        return

    # ── --daily (one competitor per day, rotated by date) ─────────────────────
    if args.daily:
        from datetime import date as _date

        # On Mondays, also refresh the competitor list (Agent 1)
        weekday = _date.today().weekday()  # 0=Mon, 6=Sun
        if weekday == 0:
            log("=== Monday — running Agent 1 (competitor discovery) first ===")
            run_agent1()
            time.sleep(2)

        tracked = read_tracked_competitors()
        if not tracked:
            log("ERROR: No Track-status competitors in Competitors tab. Nothing to do.")
            sys.exit(1)

        # Deterministic rotation: today's ordinal mod list length
        # (Same day of year always picks the same competitor — nice for spot-checking)
        idx = _date.today().toordinal() % len(tracked)
        today_target = tracked[idx]

        log(f"=== Daily target: [{idx + 1}/{len(tracked)}] {today_target['name']} ===")

        name = today_target["name"]
        website = today_target["website"]
        domain = _domain_from_website(website)
        slug = name.lower().replace(" ", "_")

        result = run_one(
            slug=slug,
            name_override=name,
            domain_override=domain,
            tab_override=name,
        )
        _print_summary([result], f"Daily run — {name}")
        return

    # ── --all-agents (full chain, v2: Competitors tab is source of truth) ────
    if args.all_agents:
        # Step 1: Agent 1 — discover new + auto-seed the 14 existing (idempotent)
        run_agent1()
        time.sleep(2)

        # Step 2: Read Competitors tab, process ALL rows where Status = "Track"
        tracked = read_tracked_competitors()
        log(f"=== Competitors tab: {len(tracked)} row(s) with Status='Track' ===")

        summary = []
        for t in tracked:
            name = t["name"]
            website = t["website"]
            domain = _domain_from_website(website)
            # Slug — used only internally for logging; tab uses exact Name
            slug = name.lower().replace(" ", "_")
            summary.append(run_one(
                slug=slug,
                name_override=name,
                domain_override=domain,
                tab_override=name,   # tab name = row's Name (auto-created by push_partners if missing)
            ))
            time.sleep(2)

        _print_summary(summary, "Summary — full 3-agent chain (Competitors tab driven)")


if __name__ == "__main__":
    main()
