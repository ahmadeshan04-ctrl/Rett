"""
NLP analysis pipeline for Rett Syndrome community comments.
Uses Anthropic API (Claude Sonnet) to classify comments and generate synthesis memo.
"""

import json
import os
import sys
from pathlib import Path

import anthropic

OUTPUT_DIR = Path(__file__).parent / "output"
MODEL = "claude-sonnet-4-20250514"

THEME_VOCABULARY = [
    "hand_use_recovery",
    "speech_communication",
    "seizure_control",
    "mobility_walking",
    "eye_contact_social",
    "GI_issues",
    "sleep",
    "breathing_irregularities",
    "emotional_wellbeing_parent",
    "trial_access_logistics",
    "ICV_surgery_fear",
    "ITL_preference",
    "safety_concern_general",
    "death_event_reaction",
    "hope_excitement",
    "skepticism_gene_therapy",
    "cost_access_insurance",
    "comparison_between_therapies",
    "other",
]

CLASSIFICATION_SYSTEM_PROMPT = """You are an expert analyst specializing in rare disease patient communities and gene therapy sentiment analysis. You are analyzing comments from Facebook pages related to Rett Syndrome (RTT).

Context:
- Two leading gene therapies are being discussed:
  - NGN-401 by Neurogene (ticker: NGNE) — delivered via intracerebroventricular (ICV) injection (surgery)
  - TSHA-102 by Taysha Gene Therapies (ticker: TSHA) — delivered via intrathecal lumbar (ITL) injection (less invasive)
- Parents and caregivers discuss these therapies, clinical trials, symptoms, and quality of life.
- A patient death occurred in the Neurogene trial, which is a significant community event.

For each comment, extract the following fields as JSON:

1. therapy_mention: one of ["NGNE", "TSHA", "both", "neither"]
   - NGNE aliases: Neurogene, NGN-401, "the Neurogene trial", "Neurogene's therapy"
   - TSHA aliases: Taysha, TSHA-102, "Taysha's therapy", "the Taysha trial"

2. sentiment_toward_NGNE: one of ["positive", "negative", "neutral", "not_mentioned"]

3. sentiment_toward_TSHA: one of ["positive", "negative", "neutral", "not_mentioned"]

4. themes: list of tags from this controlled vocabulary:
   hand_use_recovery, speech_communication, seizure_control, mobility_walking,
   eye_contact_social, GI_issues, sleep, breathing_irregularities,
   emotional_wellbeing_parent, trial_access_logistics, ICV_surgery_fear,
   ITL_preference, safety_concern_general, death_event_reaction,
   hope_excitement, skepticism_gene_therapy, cost_access_insurance,
   comparison_between_therapies, other
   If "other", include a free-text note in an "other_note" field.

5. notable_quote: boolean — is this comment particularly candid, emotionally resonant, or scientifically informed?

6. verbatim_quote: if notable_quote is true, extract the most impactful verbatim quote from the comment. Otherwise null.

7. implied_lean: one of ["NGNE", "TSHA", "neither", "unclear"]
   Even without explicit mention, does the parent's concern or preference directionally favor one therapy's profile?
   Examples:
   - Fear of surgery → TSHA lean (ITL is less invasive)
   - Desire for full gene restoration / maximum efficacy → NGNE lean
   - Concern about the patient death → TSHA lean
   - Preference for less invasive delivery → TSHA lean
   - Enthusiasm about Neurogene's data → NGNE lean

Return a JSON array of objects, one per comment, in the same order as the input.
Each object must have all 7 fields (plus optional other_note).
Return ONLY valid JSON, no markdown formatting or extra text."""


def load_comments() -> list[dict]:
    """Load all comments from raw_posts.json."""
    posts_file = OUTPUT_DIR / "raw_posts.json"
    if not posts_file.exists():
        print(f"ERROR: {posts_file} not found. Run scraper.py first.")
        sys.exit(1)

    with open(posts_file, "r", encoding="utf-8") as f:
        posts = json.load(f)

    comments = []
    for post in posts:
        for comment in post.get("comments", []):
            comment["post_id"] = post["id"]
            comment["post_text_snippet"] = post.get("post_text", "")[:200]
            comments.append(comment)

    return comments


def batch_comments(comments: list[dict], batch_size: int = 20) -> list[list[dict]]:
    """Split comments into batches."""
    return [
        comments[i : i + batch_size] for i in range(0, len(comments), batch_size)
    ]


def classify_batch(client: anthropic.Anthropic, batch: list[dict]) -> list[dict]:
    """Classify a batch of comments using the Anthropic API."""
    # Prepare input: just comment text with index
    input_data = []
    for i, comment in enumerate(batch):
        input_data.append(
            {
                "index": i,
                "comment_id": comment["id"],
                "text": comment["text"],
                "post_context": comment.get("post_text_snippet", ""),
            }
        )

    user_message = (
        "Classify each of the following comments from Rett Syndrome community "
        "Facebook pages. Return a JSON array with one classification object per comment.\n\n"
        f"Comments:\n{json.dumps(input_data, indent=2)}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=CLASSIFICATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    # Parse response
    response_text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1]
        if response_text.endswith("```"):
            response_text = response_text.rsplit("```", 1)[0]

    try:
        classifications = json.loads(response_text)
    except json.JSONDecodeError:
        print(f"  WARNING: Failed to parse API response as JSON. Returning empty.")
        classifications = []

    # Merge classifications back with original comment data
    results = []
    for i, comment in enumerate(batch):
        if i < len(classifications):
            merged = {**comment, **classifications[i]}
        else:
            merged = {
                **comment,
                "therapy_mention": "neither",
                "sentiment_toward_NGNE": "not_mentioned",
                "sentiment_toward_TSHA": "not_mentioned",
                "themes": ["other"],
                "notable_quote": False,
                "verbatim_quote": None,
                "implied_lean": "unclear",
            }
        results.append(merged)

    return results


def generate_synthesis(client: anthropic.Anthropic, analyzed: list[dict]) -> str:
    """Generate the synthesis research memo using Claude."""
    # Prepare summary stats
    total = len(analyzed)
    ngne_mentions = sum(1 for c in analyzed if c.get("therapy_mention") in ["NGNE", "both"])
    tsha_mentions = sum(1 for c in analyzed if c.get("therapy_mention") in ["TSHA", "both"])

    ngne_positive = sum(1 for c in analyzed if c.get("sentiment_toward_NGNE") == "positive")
    ngne_negative = sum(1 for c in analyzed if c.get("sentiment_toward_NGNE") == "negative")
    tsha_positive = sum(1 for c in analyzed if c.get("sentiment_toward_TSHA") == "positive")
    tsha_negative = sum(1 for c in analyzed if c.get("sentiment_toward_TSHA") == "negative")

    lean_ngne = sum(1 for c in analyzed if c.get("implied_lean") == "NGNE")
    lean_tsha = sum(1 for c in analyzed if c.get("implied_lean") == "TSHA")

    # Theme counts
    theme_counts = {}
    for c in analyzed:
        for theme in c.get("themes", []):
            theme_counts[theme] = theme_counts.get(theme, 0) + 1

    # Notable quotes
    notable = [c for c in analyzed if c.get("notable_quote")]

    stats_summary = {
        "total_comments": total,
        "ngne_mentions": ngne_mentions,
        "tsha_mentions": tsha_mentions,
        "ngne_positive": ngne_positive,
        "ngne_negative": ngne_negative,
        "tsha_positive": tsha_positive,
        "tsha_negative": tsha_negative,
        "implied_lean_ngne": lean_ngne,
        "implied_lean_tsha": lean_tsha,
        "theme_counts": dict(sorted(theme_counts.items(), key=lambda x: -x[1])),
        "notable_quotes_count": len(notable),
    }

    # Prepare notable quotes for the memo
    quotes_for_memo = []
    for q in notable[:50]:
        quotes_for_memo.append(
            {
                "author": q.get("author_anon", "Unknown"),
                "text": q.get("verbatim_quote") or q.get("text", "")[:300],
                "themes": q.get("themes", []),
                "implied_lean": q.get("implied_lean", "unclear"),
                "sentiment_ngne": q.get("sentiment_toward_NGNE", "not_mentioned"),
                "sentiment_tsha": q.get("sentiment_toward_TSHA", "not_mentioned"),
            }
        )

    synthesis_prompt = f"""You are writing a structured investment research memo analyzing Rett Syndrome (RTT) community sentiment from Facebook. This is alternative data research for evaluating gene therapy companies Neurogene (NGNE, therapy NGN-401, ICV delivery) and Taysha (TSHA, therapy TSHA-102, ITL delivery).

Here are the quantitative statistics from NLP analysis of {total} community comments:

{json.dumps(stats_summary, indent=2)}

Here are the notable quotes (anonymized):

{json.dumps(quotes_for_memo, indent=2)}

Write a structured research memo (1500-2500 words) with these exact sections:

**Section 1: Overall Community Sentiment**
General tone, hope vs. fear, sophistication level of scientific understanding among parents.

**Section 2: Therapy Preference Signals**
Which therapy do parents lean toward and why? Quote specific anonymized comments as evidence.

**Section 3: Clinically Unaddressed Concerns**
What disease burden themes appear frequently in parent discourse that are NOT primary endpoints in either trial? (e.g., GI, sleep, emotional/behavioral, breathing). For each theme, note whether it directionally maps to either therapy's known mechanism or delivery advantages.

**Section 4: The ICV Question**
How do parents actually talk about surgery fear vs. efficacy tradeoff? Does it match or contradict KOL feedback?

**Section 5: Reaction to the NGNE Patient Death**
How did the community process it? Did it shift stated preferences?

**Section 6: Implications for Commercial Uptake**
Based purely on community discourse, what would drive adoption of each therapy if both were approved?

Use direct anonymized quotes as evidence throughout. Be specific, data-driven, and write in the style of a sell-side equity research note. Do not hedge excessively — be direct about what the data shows."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": synthesis_prompt}],
    )

    return response.content[0].text


def run_analysis():
    """Main analysis entry point."""
    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY from environment

    # Load comments
    comments = load_comments()
    if not comments:
        print("No comments found to analyze.")
        return 0

    print(f"Loaded {len(comments)} comments for analysis")

    # PASS 1: Per-comment classification
    print("\n" + "=" * 60)
    print("PASS 1: Per-Comment Classification")
    print("=" * 60)

    batches = batch_comments(comments, batch_size=20)
    all_analyzed = []
    api_calls = 0

    for i, batch in enumerate(batches):
        print(f"  Batch {i + 1}/{len(batches)} ({len(batch)} comments)...")
        try:
            results = classify_batch(client, batch)
            all_analyzed.extend(results)
            api_calls += 1
        except Exception as e:
            print(f"    ERROR in batch {i + 1}: {e}")
            # Add unclassified entries
            for comment in batch:
                all_analyzed.append(
                    {
                        **comment,
                        "therapy_mention": "neither",
                        "sentiment_toward_NGNE": "not_mentioned",
                        "sentiment_toward_TSHA": "not_mentioned",
                        "themes": ["other"],
                        "notable_quote": False,
                        "verbatim_quote": None,
                        "implied_lean": "unclear",
                        "classification_error": str(e),
                    }
                )

    # Save analyzed comments
    analyzed_file = OUTPUT_DIR / "analyzed_comments.json"
    with open(analyzed_file, "w", encoding="utf-8") as f:
        json.dump(all_analyzed, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {analyzed_file} ({len(all_analyzed)} entries)")

    # PASS 2: Synthesis memo
    print("\n" + "=" * 60)
    print("PASS 2: Generating Synthesis Memo")
    print("=" * 60)

    try:
        memo = generate_synthesis(client, all_analyzed)
        api_calls += 1
        memo_file = OUTPUT_DIR / "synthesis_memo.txt"
        with open(memo_file, "w", encoding="utf-8") as f:
            f.write(memo)
        print(f"Wrote {memo_file}")
    except Exception as e:
        print(f"ERROR generating synthesis: {e}")

    return api_calls


if __name__ == "__main__":
    calls = run_analysis()
    print(f"\n{'=' * 60}")
    print(f"ANALYSIS SUMMARY")
    print(f"  API calls made: {calls}")
    print(f"{'=' * 60}")
