"""
scheduler/daily_runner.py
==========================
Phase 4 — Daily Scheduler

Responsibility:
  - Run the complete pipeline once per day
  - Log every run with timestamp
  - Send a summary report (optional)
  - Can be triggered by cron, Task Scheduler, or run manually

How to schedule:

  LINUX / MAC (cron):
    Open terminal → run: crontab -e
    Add this line (runs every day at 08:00):
    0 8 * * * cd /path/to/job-application-agent && python scheduler/daily_runner.py >> logs/cron.log 2>&1

  WINDOWS (Task Scheduler):
    1. Open Task Scheduler
    2. Create Basic Task → Daily → 08:00
    3. Action: Start a program
       Program: python
       Arguments: scheduler/daily_runner.py
       Start in: C:\\path\\to\\job-application-agent

  MANUAL:
    python scheduler/daily_runner.py
    python scheduler/daily_runner.py --force   (re-run even if already ran today)

Pipeline order:
  1. Apify Collector  (live jobs from LinkedIn/Indeed)
  2. Job Cleaner      (deduplicate + normalize)
  3. Job Matcher      (score all jobs)
  4. CV Tailor        (generate CVs for score >= 85)
  5. Obsidian Sync    (update vault notes)
  6. Google Drive     (upload CVs and tracker)
  7. Tracker Update   (write tracker.csv)
"""

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

# Ensure we can import from parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.apify_collector import run as run_apify
from agents.job_cleaner     import run as run_cleaner
from agents.job_matcher     import run as run_matcher
from agents.cv_tailor       import run as run_cv_tailor
from agents.tracker_updater import update_tracker
from integrations.obsidian_sync  import run as run_obsidian_sync
from integrations.google_drive   import run as run_google_drive


# ── Logging setup ──────────────────────────────────────────────────────────────

def setup_logging(log_dir: str = "logs") -> logging.Logger:
    Path(log_dir).mkdir(exist_ok=True)
    today = str(date.today())
    log_file = f"{log_dir}/pipeline_{today}.log"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler (daily log file)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logging.getLogger("daily_runner")


# ── Run state tracking ─────────────────────────────────────────────────────────

def get_run_state_file(log_dir: str = "logs") -> Path:
    return Path(log_dir) / "last_run.json"


def already_ran_today(log_dir: str = "logs") -> bool:
    """Check if pipeline already ran successfully today."""
    state_file = get_run_state_file(log_dir)
    if not state_file.exists():
        return False
    try:
        state = json.loads(state_file.read_text())
        return state.get("date") == str(date.today()) and state.get("status") == "success"
    except Exception:
        return False


def save_run_state(summary: dict, log_dir: str = "logs") -> None:
    state_file = get_run_state_file(log_dir)
    state = {
        "date":      str(date.today()),
        "timestamp": datetime.now().isoformat(),
        "status":    "success",
        "summary":   summary,
    }
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def save_run_history(summary: dict, log_dir: str = "logs") -> None:
    """Append this run to a cumulative history file."""
    history_file = Path(log_dir) / "run_history.json"
    history = []
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text())
        except Exception:
            history = []
    history.append({
        "date":      str(date.today()),
        "timestamp": datetime.now().isoformat(),
        **summary,
    })
    # Keep last 90 days
    history = history[-90:]
    history_file.write_text(json.dumps(history, indent=2), encoding="utf-8")


# ── Pipeline runner ────────────────────────────────────────────────────────────

def run_pipeline(config_path: str = "config/config.yaml",
                 force: bool = False,
                 min_cv_score: int = 85,
                 max_cvs: int = None) -> dict:
    """
    Execute the full daily pipeline.

    Args:
        force:        Run even if already ran today
        min_cv_score: Minimum score to generate CV (default 85)
        max_cvs:      Max CVs to generate per run (None = all qualifying)

    Returns complete summary dict.
    """
    logger = logging.getLogger("daily_runner")
    today  = str(date.today())

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    log_dir = config.get("paths", {}).get("logs", "logs")

    logger.info("=" * 60)
    logger.info(f"DAILY PIPELINE — {today}")
    logger.info("=" * 60)

    summary = {
        "date":           today,
        "collected":      0,
        "cleaned":        0,
        "rejected_clean": 0,
        "scored":         0,
        "excellent":      0,
        "high":           0,
        "medium":         0,
        "rejected_score": 0,
        "cvs_generated":  0,
        "errors":         [],
    }

    # ── Step 1: Apify Collector ────────────────────────────────────────────────
    logger.info("\n── STEP 1/7: Apify Collector ──")
    try:
        apify_result = run_apify(config_path)
        summary["collected"] = apify_result.get("total", 0)
        status = apify_result.get("status", "unknown")
        if status == "skipped":
            logger.info("  Apify skipped (no token) — using existing mock/local data")
        elif status == "cached":
            logger.info(f"  Using cached data from today ({summary['collected']} jobs)")
        else:
            logger.info(f"  Collected {summary['collected']} new jobs")
    except Exception as e:
        logger.error(f"  Apify Collector failed: {e}")
        summary["errors"].append(f"collector: {e}")

    # ── Step 2: Job Cleaner ────────────────────────────────────────────────────
    logger.info("\n── STEP 2/7: Job Cleaner ──")
    clean_stats = {}
    try:
        clean_stats = run_cleaner(config_path)
        summary["cleaned"]        = clean_stats.get("cleaned", 0)
        summary["rejected_clean"] = clean_stats.get("rejected", 0)
        logger.info(f"  Clean: {summary['cleaned']} | Rejected: {summary['rejected_clean']}")
    except Exception as e:
        logger.error(f"  Job Cleaner failed: {e}")
        summary["errors"].append(f"cleaner: {e}")

    # ── Step 3: Job Matcher ────────────────────────────────────────────────────
    logger.info("\n── STEP 3/7: Job Matcher ──")
    match_results = {}
    try:
        # Point matcher at cleaned output
        cleaned_file = Path(config["paths"]["cleaned_jobs"]) / f"cleaned_jobs_{today}.json"
        if cleaned_file.exists():
            config["mock_jobs_file"] = str(cleaned_file)
            # Write updated config back so matcher picks it up
            import tempfile, os
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
                yaml.dump(config, tmp, allow_unicode=True)
                tmp_config = tmp.name
        else:
            tmp_config = config_path

        m_summary, match_results = run_matcher(tmp_config)
        if cleaned_file.exists():
            os.unlink(tmp_config)
        summary["excellent"]      = m_summary.get("excellent", 0)
        summary["high"]           = m_summary.get("high", 0)
        summary["medium"]         = m_summary.get("medium", 0)
        summary["rejected_score"] = m_summary.get("rejected", 0)
        summary["scored"] = (
            summary["excellent"] + summary["high"] + summary["medium"]
        )
        logger.info(
            f"  Excellent: {summary['excellent']} | "
            f"High: {summary['high']} | "
            f"Medium: {summary['medium']} | "
            f"Rejected: {summary['rejected_score']}"
        )
    except Exception as e:
        logger.error(f"  Job Matcher failed: {e}")
        summary["errors"].append(f"matcher: {e}")

    # ── Step 4: CV Tailor ──────────────────────────────────────────────────────
    logger.info("\n── STEP 4/7: CV Tailor ──")
    try:
        cv_summary = run_cv_tailor(
            config_path=config_path,
            min_score=min_cv_score,
            max_cvs=max_cvs,
        )
        summary["cvs_generated"] = cv_summary.get("generated", 0)
        if cv_summary.get("errors", 0) > 0:
            summary["errors"].append(f"cv_tailor: {cv_summary['errors']} CV(s) failed")
        logger.info(f"  CVs generated: {summary['cvs_generated']}")
    except Exception as e:
        logger.error(f"  CV Tailor failed: {e}")
        summary["errors"].append(f"cv_tailor: {e}")

    # ── Step 5: Tracker Updater ────────────────────────────────────────────────
    logger.info("\n── STEP 5/7: Tracker Updater ──")
    try:
        kept = (
            match_results.get("excellent", []) +
            match_results.get("high",      []) +
            match_results.get("medium",    [])
        )
        t_stats = update_tracker(kept, config["paths"]["tracker"])
        logger.info(
            f"  Added: {t_stats['added']} | "
            f"Protected: {t_stats['skipped_protected']} | "
            f"Refreshed: {t_stats['updated_score']}"
        )
    except Exception as e:
        logger.error(f"  Tracker Updater failed: {e}")
        summary["errors"].append(f"tracker: {e}")

    # ── Step 6: Obsidian Sync ──────────────────────────────────────────────────
    logger.info("\n── STEP 6/7: Obsidian Sync ──")
    try:
        kept_jobs = (
            match_results.get("excellent", []) +
            match_results.get("high",      []) +
            match_results.get("medium",    [])
        )
        obs_stats = run_obsidian_sync(
            config_path=config_path,
            scored_jobs=kept_jobs,
            rejected_count=summary["rejected_score"],
            clean_stats=clean_stats,
        )
        logger.info(
            f"  Job notes: {obs_stats.get('job_notes', 0)} | "
            f"Tracker: {'✓' if obs_stats.get('tracker_updated') else '✗'} | "
            f"Summary: {'✓' if obs_stats.get('daily_summary') else '✗'}"
        )
    except Exception as e:
        logger.error(f"  Obsidian Sync failed: {e}")
        summary["errors"].append(f"obsidian: {e}")

    # ── Step 7: Daily Apply Page ────────────────────────────────────────────────
    logger.info("\n── STEP 7/8: Daily Apply Page ──")
    try:
        from agents.daily_apply_page import generate_daily_page
        generate_daily_page(
            tracker_path=config["paths"]["tracker"],
            vault_path=config.get("obsidian_vault", "../MinaJobAgentVault"),
        )
        logger.info("  ✓ Daily apply page created in Obsidian")
    except Exception as e:
        logger.error(f"  Daily apply page failed: {e}")
        summary["errors"].append(f"daily_apply_page: {e}")

    # ── Step 7: Google Drive ───────────────────────────────────────────────────
    logger.info("\n── STEP 7/7: Google Drive ──")
    try:
        drive_result = run_google_drive(config_path)
        status = drive_result.get("status", "unknown")
        if status == "disabled":
            logger.info("  Google Drive sync disabled (set google_drive.enabled: true to activate)")
        elif status == "no_credentials":
            logger.info("  Google Drive skipped — credentials not configured")
        else:
            logger.info(
                f"  CVs: {drive_result.get('cvs_uploaded', 0)} | "
                f"Tracker: {'✓' if drive_result.get('tracker_uploaded') else '✗'}"
            )
    except Exception as e:
        logger.error(f"  Google Drive failed: {e}")
        summary["errors"].append(f"drive: {e}")

    # ── Final summary ──────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("DAILY PIPELINE COMPLETE")
    logger.info(f"  Date         : {today}")
    logger.info(f"  Collected    : {summary['collected']}")
    logger.info(f"  Cleaned      : {summary['cleaned']}")
    logger.info(f"  Scored (kept): {summary['scored']}")
    logger.info(f"  CVs generated: {summary['cvs_generated']}")
    if summary["errors"]:
        logger.warning(f"  Errors       : {len(summary['errors'])}")
        for err in summary["errors"]:
            logger.warning(f"    - {err}")
    logger.info("=" * 60)

    save_run_state(summary, log_dir)
    save_run_history(summary, log_dir)

    return summary


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Mina Job Agent — Daily Runner")
    parser.add_argument("--config",     default="config/config.yaml")
    parser.add_argument("--force",      action="store_true",
                        help="Run even if already ran today")
    parser.add_argument("--min-score",  type=int, default=85,
                        help="Minimum score for CV generation")
    parser.add_argument("--max-cvs",    type=int, default=None,
                        help="Max CVs to generate per run")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Run without generating CVs (testing)")
    args = parser.parse_args()

    logger = setup_logging()

    # Check if already ran today
    if not args.force and already_ran_today():
        logger.info(f"Pipeline already ran successfully today ({date.today()}). Use --force to re-run.")
        sys.exit(0)

    min_score = 999 if args.dry_run else args.min_score
    summary   = run_pipeline(
        config_path=args.config,
        force=args.force,
        min_cv_score=min_score,
        max_cvs=args.max_cvs,
    )

    exit_code = 1 if summary.get("errors") else 0
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
