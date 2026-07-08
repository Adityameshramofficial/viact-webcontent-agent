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
from enrich_partners import enrich_tab
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
    except Exception as e:
        log(f"  SHEET PUSH FAILED: {e}")
        return {"slug": slug, "discovered": len(rows), "appended": 0,
                "email_hits": 0, "phone_hits": 0, "error": str(e)}

    # v3.2: Agent 2 done. Now chain Agent 3 (enrichment) as a SEPARATE step.
    # This runs on the exact rows we just pushed (plus any older blank ones).
    log(f"  [Agent 3] Enriching contacts for '{tab}'...")
    try:
        # domain_override is the competitor's own domain from the slug lookup;
        # for ad-hoc competitors we use domain_override argument directly.
        actual_domain = domain_override or (
            COMPETITOR_MAP.get(slug, {}).get("domain", "")
        )
        enrich_result = enrich_tab(
            tab,
            competitor_domain=actual_domain,
            overwrite=False,
            progress=lambda m: log(f"    {m}"),
        )
        log(f"  Enrichment: {enrich_result['email_hits']} emails, "
            f"{enrich_result['phone_hits']} phones added")
        return {"slug": slug, "discovered": len(rows), "appended": appended,
                "email_hits": enrich_result["email_hits"],
                "phone_hits": enrich_result["phone_hits"], "error": None}
    except Exception as e:
        log(f"  ENRICHMENT FAILED: {e}")
        return {"slug": slug, "discovered": len(rows), "appended": appended,
                "email_hits": 0, "phone_hits": 0, "error": str(e)}


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
    total_emails = sum(s.get("email_hits", 0) for s in summary)
    total_phones = sum(s.get("phone_hits", 0) for s in summary)
    failed = [s for s in summary if s["error"]]
    log(f"  Discovered: {total_disc} partners across {len(summary)} competitor(s)")
    log(f"  Appended:   {total_app} new rows to sheets")
    log(f"  Enriched:   {total_emails} emails, {total_phones} phones")
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
    group.add_argument("--enrich",
                       help="Agent 3 alone — re-enrich contact info for one existing competitor tab. "
                            "Reads rows with blank Email and tries to fill them. No new discovery.")
    group.add_argument("--enrich-all", action="store_true",
                       help="Agent 3 alone — re-enrich all Track-status tabs. Same as --enrich but "
                            "loops over all tracked competitors.")
    group.add_argument("--fill-missing",
                       help="Agent 3.5 alone — fill blank Description/Address/Country/Phone in one tab "
                            "via free stack (Jina + Groq 8B). Doesn't re-scrape email if already there.")
    group.add_argument("--fill-missing-all", action="store_true",
                       help="Fill missing fields across all Track-status tabs.")
    parser.add_argument("--overwrite", action="store_true",
                       help="For --enrich / --enrich-all: also re-scrape rows that already have "
                            "Email filled (useful after strict-validation upgrade).")
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

    # ── --enrich (Agent 3 alone on one tab) ───────────────────────────────────
    if args.enrich:
        from enrich_partners import _competitor_domain_for_tab
        from push_to_sheets import get_sheets_service as _gss
        service = _gss()
        sheet_id = os.getenv("PARTNER_SHEET_ID", "")
        domain = _competitor_domain_for_tab(service, sheet_id, args.enrich)
        if not domain:
            log(f"WARN: cannot auto-detect competitor domain for '{args.enrich}'.")
        result = enrich_tab(
            args.enrich,
            competitor_domain=domain,
            overwrite=args.overwrite,
            progress=lambda m: log(f"  {m}"),
        )
        log(f"Result: {result['email_hits']} emails, {result['phone_hits']} phones added")
        return

    # ── --fill-missing (Agent 3.5 on one tab) ─────────────────────────────────
    if args.fill_missing:
        from fill_missing_fields import fill_tab
        result = fill_tab(args.fill_missing, progress=lambda m: log(f"  {m}"))
        log(f"Result: {result}")
        return

    # ── --fill-missing-all ────────────────────────────────────────────────────
    if args.fill_missing_all:
        from fill_missing_fields import fill_tab
        tracked = read_tracked_competitors()
        log(f"Filling missing fields for {len(tracked)} tracked tabs...")
        totals = {"descriptions": 0, "phones": 0, "addresses": 0, "countries": 0}
        for t in tracked:
            log(f"=== {t['name']} ===")
            r = fill_tab(t["name"], progress=lambda m: log(f"  {m}"))
            for k in totals:
                totals[k] += r[k]
            time.sleep(1)
        log(f"=== TOTALS: descs={totals['descriptions']} phones={totals['phones']} "
            f"addrs={totals['addresses']} countries={totals['countries']} ===")
        return

    # ── --enrich-all (Agent 3 alone on all Track tabs) ────────────────────────
    if args.enrich_all:
        from enrich_partners import _competitor_domain_for_tab
        from push_to_sheets import get_sheets_service as _gss
        service = _gss()
        sheet_id = os.getenv("PARTNER_SHEET_ID", "")
        tracked = read_tracked_competitors()
        log(f"Enriching {len(tracked)} Track-status tabs...")
        total_emails = total_phones = 0
        for t in tracked:
            tab_name = t["name"]
            domain = _competitor_domain_for_tab(service, sheet_id, tab_name)
            log(f"=== {tab_name} ===")
            result = enrich_tab(
                tab_name,
                competitor_domain=domain,
                overwrite=args.overwrite,
                progress=lambda m: log(f"  {m}"),
            )
            total_emails += result["email_hits"]
            total_phones += result["phone_hits"]
            time.sleep(1)
        log(f"=== TOTAL: {total_emails} emails, {total_phones} phones ===")
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

        # v4.1: chain fill_missing after enrichment so every daily run also
        # populates Description / Country (via TLD) / Phone / Address gaps
        try:
            from fill_missing_fields import fill_tab
            log(f"=== fill_missing for {name} ===")
            fm = fill_tab(name, progress=lambda m: log(f"  {m}"))
            log(f"  fill_missing added: desc={fm['descriptions']} "
                f"country={fm['countries']} phone={fm['phones']} addr={fm['addresses']}")
        except Exception as e:
            log(f"  fill_missing failed (non-fatal): {e}")

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
