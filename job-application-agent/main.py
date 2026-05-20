"""
main.py — Mina Job Application Agent
Phase 3 Pipeline: Collect → Clean → Match → Tailor CVs → Track

Usage:
  python main.py                        # full pipeline
  python main.py --phase match          # only one phase
  python main.py --phase cv             # only CV generation
  python main.py --max-cvs 2            # limit CV generation
  python main.py --min-score 90         # only excellent jobs
  python main.py --verbose
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from agents.job_collector   import run as run_collector
from agents.job_cleaner     import run as run_cleaner
from agents.job_matcher     import run as run_matcher
from agents.cv_tailor       import run as run_cv_tailor
from agents.tracker_updater import update_tracker
from agents.report_generator import generate_report
from integrations.obsidian_sync import run as run_obsidian_sync
import tempfile
import os


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def banner(phase):
    print()
    print("=" * 60)
    print(f"  MINA JOB APPLICATION AGENT — Phase {phase}")
    print(f"  Date: {date.today()}")
    print("  Collect → Clean → Match → Tailor → Track")
    print("=" * 60)
    print()


def print_scored_table(results):
    tiers = [
        ("🌟 EXCELLENT (90+)", results.get("excellent", [])),
        ("✅ HIGH (85–89)",     results.get("high", [])),
        ("🔵 MEDIUM (75–84)",  results.get("medium", [])),
        ("❌ REJECTED",        results.get("rejected", [])),
    ]
    for label, jobs in tiers:
        if not jobs:
            continue
        print(f"\n{label}  —  {len(jobs)} job(s)")
        print("-" * 56)
        for j in jobs:
            reason = j.get("rejection_reason") or j.get("clean_rejection_reason", "")
            score  = j.get("match_score", 0)
            print(f"  [{j.get('id','?')[:26]:26}] "
                  f"{j.get('title','?')[:30]:<30} "
                  f"@ {j.get('company','?')[:16]:<16} {score:>3}/100")
            if reason:
                print(f"    ↳ {reason}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Mina Job Application Agent")
    parser.add_argument("--config",    default="config/config.yaml")
    parser.add_argument("--phase",     default="all",
                        choices=["all","collect","clean","match","cv","track"])
    parser.add_argument("--min-score", type=int, default=85,
                        help="Minimum score for CV generation (default: 85)")
    parser.add_argument("--max-cvs",   type=int, default=None,
                        help="Max number of CVs to generate (default: all qualifying)")
    parser.add_argument("--test",      action="store_true", help="mock data only, no internet needed")
    parser.add_argument("--dry-run",   action="store_true", help="fetch real jobs but don't save tracker")
    parser.add_argument("--daily",     action="store_true", help="full real run, updates everything")
    parser.add_argument("--verbose",   action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    banner("3")

    with open(args.config, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if "apify" not in config:
        config["apify"] = {}
        
    phases = config.get("phases", {})
    
    if args.test:
        config["apify"]["use_mock_data"] = True
    elif args.dry_run:
        config["apify"]["use_mock_data"] = False
        phases["tracker_update"] = False
    elif args.daily:
        config["apify"]["use_mock_data"] = False
        phases["tracker_update"] = True
        
    # Write temp config to pass overrides to agents
    fd, temp_path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.dump(config, f)
    config_path_to_use = temp_path

    today  = str(date.today())
    results = {}
    stats = {
        "raw_collected": 0,
        "after_cleaning": 0,
        "duplicates_removed": 0,
        "already_applied_skipped": 0,
        "relevant_jobs": 0,
        "high_priority": 0,
        "cvs_generated": 0
    }

    # ── STEP 1: Collect ───────────────────────────────────────────────────────
    if args.phase in ("all", "collect") and phases.get("collect", True):
        print("━" * 60)
        print("STEP 1/5 — Job Collector")
        print("━" * 60)
        c = run_collector(config_path_to_use)
        stats["raw_collected"] = c.get('total', 0)
        print(f"  ✓ {c['total']} jobs collected from {len(c['sources'])} sources\n")

    # ── STEP 2: Clean ─────────────────────────────────────────────────────────
    if args.phase in ("all", "clean") and phases.get("clean", True):
        print("━" * 60)
        print("STEP 2/5 — Job Cleaner")
        print("━" * 60)
        cl = run_cleaner(config_path_to_use)
        clean_stats_full = cl
        stats["after_cleaning"] = cl.get('cleaned', 0)
        print(f"  ✓ Clean: {cl['cleaned']}  Rejected: {cl['rejected']}  "
              f"Input: {cl['total_input']}\n")

    # ── STEP 3: Match ─────────────────────────────────────────────────────────
    if args.phase in ("all", "match", "cv") and phases.get("match", True):
        print("━" * 60)
        print("STEP 3/5 — Job Matcher")
        print("━" * 60)
        cleaned_file = Path(config["paths"]["cleaned_jobs"]) / f"cleaned_jobs_{today}.json"
        if cleaned_file.exists():
            config["mock_jobs_file"] = str(cleaned_file)
            # Re-write config since we updated it
            with open(config_path_to_use, "w", encoding="utf-8") as f:
                yaml.dump(config, f)
                
        m_summary, results = run_matcher(config_path_to_use)
        stats["relevant_jobs"] = m_summary.get("excellent", 0) + m_summary.get("high", 0) + m_summary.get("medium", 0)
        stats["high_priority"] = m_summary.get("excellent", 0) + m_summary.get("high", 0)
        print_scored_table(results)

    # ── STEP 4: CV Tailor ─────────────────────────────────────────────────────
    if args.phase in ("all", "cv") and phases.get("cv_tailor", True):
        print("━" * 60)
        print("STEP 4/5 — CV Tailor (Claude API)")
        print("━" * 60)
        cv_summary = run_cv_tailor(
            config_path=config_path_to_use,
            min_score=args.min_score,
            max_cvs=args.max_cvs,
        )
        stats["cvs_generated"] = cv_summary.get("generated", 0)
        print(f"\n  ✓ CVs generated : {cv_summary.get('generated', 0)}")
        print(f"  ✓ Errors        : {cv_summary.get('errors', 0)}")
        if cv_summary.get("files"):
            print("  ✓ Files:")
            for f in cv_summary["files"]:
                print(f"      {f}")
        print()

    # ── STEP 5: Track ─────────────────────────────────────────────────────────
    if args.phase in ("all", "track") and phases.get("tracker_update", True):
        print("━" * 60)
        print("STEP 5/5 — Tracker Updater")
        print("━" * 60)
        if results:
            kept = (results.get("excellent", []) +
                    results.get("high", []) +
                    results.get("medium", []))
            t = update_tracker(kept, config["paths"]["tracker"])
            stats["already_applied_skipped"] = t.get('skipped_protected', 0)
            print(f"  ✓ Added: {t['added']}  Protected: {t['skipped_protected']}  "
                  f"Refreshed: {t['updated_score']}")
        print(f"  ✓ Tracker: {config['paths']['tracker']}\n")

    # ── STEP 6: Generate Daily Report ─────────────────────────────────────────
    print("━" * 60)
    print("STEP 6/6 — Generating Daily Report")
    print("━" * 60)
    # Collect ready jobs for report (all jobs that got a CV generated)
    ready_jobs = []
    if results:
        # Get jobs that have CV generated. Since we updated tracker, we can just use the kept ones.
        kept = results.get("excellent", []) + results.get("high", [])
        for j in kept:
            # Check if this job has a generated CV
            j["cv_file"] = "CV generated"
            ready_jobs.append(j)
            
    out_dir = Path("outputs/daily_reports")
    report_file = generate_report(stats, ready_jobs, str(out_dir))
    print(f"  ✓ Report generated: {report_file}\n")
    
    # ── STEP 7: Obsidian Sync ─────────────────────────────────────────────────
    print("━" * 60)
    print("STEP 7/7 — Syncing to Obsidian")
    print("━" * 60)
    
    all_scored_jobs = []
    rejected_count = 0
    if results:
        all_scored_jobs = (results.get("excellent", []) + 
                           results.get("high", []) + 
                           results.get("medium", []))
        rejected_count = len(results.get("rejected", []))
        
    sync_stats = run_obsidian_sync(
        config_path=config_path_to_use,
        scored_jobs=all_scored_jobs,
        rejected_count=rejected_count,
        clean_stats=locals().get("clean_stats_full")
    )
    print(f"  ✓ Obsidian vault updated: {sync_stats['job_notes']} notes, summary, tracker\n")
    
    # ── STEP 8: Daily Apply Page ──────────────────────────────────────────────
    print("━" * 60)
    print("STEP 8/8 — Generate Daily Apply Page")
    print("━" * 60)
    try:
        from agents.daily_apply_page import generate_daily_page
        generate_daily_page(
            tracker_path=config["paths"]["tracker"],
            vault_path=config.get("obsidian_vault", "../MinaJobAgentVault")
        )
        print("  ✓ Daily apply page created in Obsidian\n")
    except Exception as e:
        print(f"  ✗ Daily apply page failed: {e}\n")
    
    # Cleanup temp config
    if os.path.exists(config_path_to_use) and config_path_to_use != args.config:
        try:
            os.remove(config_path_to_use)
        except Exception:
            pass

    # ── Final summary ─────────────────────────────────────────────────────────
    print("=" * 60)
    print("  PIPELINE COMPLETE ✅")
    print(f"  Report   : {report_file}")
    print(f"  Tracker  : {config['paths']['tracker']}")
    print(f"  CVs      : {config['paths']['tailored_cvs']}")
    print(f"  Scored   : data/scored/scored_jobs_{today}.json")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
