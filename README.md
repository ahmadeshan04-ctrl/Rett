# RTT Community Sentiment Analysis Pipeline

Facebook scraping + NLP analysis pipeline for investment research on Rett Syndrome gene therapies (NGNE vs TSHA).

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Authentication

Export your Facebook cookies using a browser extension (EditThisCookie or Cookie-Editor) and save as `cookies.json` in the project root.

## Usage

```bash
# Full pipeline
python pipeline.py

# Individual stages
python pipeline.py --scrape       # Scrape Facebook only
python pipeline.py --analyze      # NLP analysis only
python pipeline.py --dashboard    # Generate HTML dashboard only
python pipeline.py --report       # Generate Word report only
python pipeline.py --no-scrape    # Skip scraping, run analysis + outputs
```

## Output Files

All outputs are written to `output/`:

| File | Description |
|------|-------------|
| `raw_posts.json` | Full scraped posts with comments (anonymized) |
| `raw_comments.csv` | Flat comment table |
| `analyzed_comments.json` | Per-comment NLP classifications |
| `synthesis_memo.txt` | Research memo (1500-2500 words) |
| `dashboard.html` | Interactive HTML dashboard with charts |
| `report.docx` | Formatted Word report with embedded charts |

## Environment

Requires `ANTHROPIC_API_KEY` environment variable for NLP analysis.
