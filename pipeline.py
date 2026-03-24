#!/usr/bin/env python3
"""
RTT Community Sentiment Analysis Pipeline
==========================================
Full pipeline: Facebook scraping → NLP analysis → Dashboard → Report

Usage:
  python pipeline.py              # Run full pipeline
  python pipeline.py --scrape     # Scrape only
  python pipeline.py --analyze    # Analyze only (requires scraped data)
  python pipeline.py --dashboard  # Generate dashboard only
  python pipeline.py --report     # Generate Word report only
  python pipeline.py --no-scrape  # Skip scraping, run analysis + outputs
"""

import argparse
import sys
import time
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"


def run_full_pipeline(skip_scrape=False, only_scrape=False, only_analyze=False,
                      only_dashboard=False, only_report=False):
    """Execute the pipeline stages."""
    start = time.time()
    pages_scraped = 0
    comments_collected = 0
    api_calls = 0
    errors = 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Stage 1: Scraping
    if not skip_scrape and not only_analyze and not only_dashboard and not only_report:
        print("\n" + "=" * 60)
        print("STAGE 1: FACEBOOK SCRAPING")
        print("=" * 60)
        import asyncio
        from scraper import run_scraper
        pages_scraped, comments_collected, scrape_errors = asyncio.run(run_scraper())
        errors += scrape_errors

    if only_scrape:
        _print_summary(pages_scraped, comments_collected, api_calls, errors, start)
        return

    # Stage 2: NLP Analysis
    if not only_dashboard and not only_report:
        print("\n" + "=" * 60)
        print("STAGE 2: NLP ANALYSIS")
        print("=" * 60)
        from analyzer import run_analysis
        api_calls = run_analysis()

    if only_analyze:
        _print_summary(pages_scraped, comments_collected, api_calls, errors, start)
        return

    # Stage 3: Dashboard
    if not only_report:
        print("\n" + "=" * 60)
        print("STAGE 3: DASHBOARD GENERATION")
        print("=" * 60)
        from dashboard import generate_dashboard
        generate_dashboard()

    if only_dashboard:
        _print_summary(pages_scraped, comments_collected, api_calls, errors, start)
        return

    # Stage 4: Word Report
    print("\n" + "=" * 60)
    print("STAGE 4: WORD REPORT GENERATION")
    print("=" * 60)
    from report import generate_report
    generate_report()

    _print_summary(pages_scraped, comments_collected, api_calls, errors, start)


def _print_summary(pages, comments, api_calls, errors, start):
    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    print(f"  Pages scraped:      {pages}")
    print(f"  Comments collected:  {comments}")
    print(f"  API calls made:      {api_calls}")
    print(f"  Errors:              {errors}")
    print(f"  Elapsed time:        {elapsed:.1f}s")
    print()
    print("Output files:")
    for f in sorted(OUTPUT_DIR.glob("*")):
        if f.is_file():
            size = f.stat().st_size
            unit = "KB" if size > 1024 else "B"
            size_display = size / 1024 if size > 1024 else size
            print(f"  {f.name:30s} {size_display:>8.1f} {unit}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RTT Sentiment Analysis Pipeline")
    parser.add_argument("--scrape", action="store_true", help="Scrape only")
    parser.add_argument("--analyze", action="store_true", help="Analyze only")
    parser.add_argument("--dashboard", action="store_true", help="Dashboard only")
    parser.add_argument("--report", action="store_true", help="Report only")
    parser.add_argument("--no-scrape", action="store_true", help="Skip scraping")
    args = parser.parse_args()

    run_full_pipeline(
        skip_scrape=args.no_scrape,
        only_scrape=args.scrape,
        only_analyze=args.analyze,
        only_dashboard=args.dashboard,
        only_report=args.report,
    )
