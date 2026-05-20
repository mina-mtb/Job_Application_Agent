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
    parser.add_argument("--verbose",   action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    banner("3")

    with open(args.config) as f:
        config = yaml.safe_load(f)

    phases = config.get("phases", {})
    today  = str(date.today())
    results = {}

    # ── STEP 1: Collect ───────────────────────────────────────────────────────
    if args.phase in ("all", "collect") and phases.get("collect", True):
        print("━" * 60)
        print("STEP 1/5 — Job Collector")
        print("━" * 60)
        c = run_collector(args.config)
        print(f"  ✓ {c['total']} jobs collected from {len(c['sources'])} sources\n")

    # ── STEP 2: Clean ─────────────────────────────────────────────────────────
    if args.phase in ("all", "clean") and phases.get("clean", True):
        print("━" * 60)
        print("STEP 2/5 — Job Cleaner")
        print("━" * 60)
        cl = run_cleaner(args.config)
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
        m_summary, results = run_matcher(args.config)
        print_scored_table(results)

    # ── STEP 4: CV Tailor ─────────────────────────────────────────────────────
    if args.phase in ("all", "cv") and phases.get("cv_tailor", True):
        print("━" * 60)
        print("STEP 4/5 — CV Tailor (Claude API)")
        print("━" * 60)
        cv_summary = run_cv_tailor(
            config_path=args.config,
            min_score=args.min_score,
            max_cvs=args.max_cvs,
        )
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
            print(f"  ✓ Added: {t['added']}  Protected: {t['skipped_protected']}  "
                  f"Refreshed: {t['updated_score']}")
        print(f"  ✓ Tracker: {config['paths']['tracker']}\n")

    # ── Final summary ─────────────────────────────────────────────────────────
    print("=" * 60)
    print("  PIPELINE COMPLETE ✅")
    print(f"  Tracker  : {config['paths']['tracker']}")
    print(f"  CVs      : {config['paths']['tailored_cvs']}")
    print(f"  Scored   : data/scored/scored_jobs_{today}.json")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
