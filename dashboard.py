"""
Generate a self-contained interactive HTML dashboard from analyzed_comments.json.
"""

import json
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"


def generate_dashboard():
    """Build dashboard.html from analyzed comment data."""
    analyzed_file = OUTPUT_DIR / "analyzed_comments.json"
    if not analyzed_file.exists():
        print(f"ERROR: {analyzed_file} not found. Run analyzer.py first.")
        return

    with open(analyzed_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Serialize data for embedding in HTML
    data_json = json.dumps(data, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RTT Community Sentiment Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; }}
.header {{ background: linear-gradient(135deg, #1e293b, #334155); padding: 24px 32px; border-bottom: 2px solid #3b82f6; }}
.header h1 {{ font-size: 24px; font-weight: 700; color: #f8fafc; }}
.header p {{ color: #94a3b8; margin-top: 4px; font-size: 14px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; padding: 24px; }}
.card {{ background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }}
.card h2 {{ font-size: 16px; color: #93c5fd; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
.stat-row {{ display: flex; gap: 16px; padding: 24px; flex-wrap: wrap; }}
.stat {{ background: #1e293b; border-radius: 12px; padding: 16px 24px; border: 1px solid #334155; min-width: 150px; text-align: center; }}
.stat .number {{ font-size: 32px; font-weight: 700; color: #3b82f6; }}
.stat .label {{ font-size: 12px; color: #94a3b8; margin-top: 4px; text-transform: uppercase; }}
.filters {{ padding: 0 24px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
.filters label {{ color: #94a3b8; font-size: 13px; }}
.filters select {{ background: #1e293b; color: #e2e8f0; border: 1px solid #475569; border-radius: 6px; padding: 6px 10px; font-size: 13px; }}
canvas {{ max-height: 300px; }}
.quote-card {{ background: #0f172a; border-left: 3px solid #3b82f6; padding: 12px 16px; margin-bottom: 10px; border-radius: 0 8px 8px 0; }}
.quote-text {{ font-style: italic; color: #cbd5e1; line-height: 1.5; }}
.quote-meta {{ font-size: 12px; color: #64748b; margin-top: 6px; }}
.quote-nav {{ display: flex; gap: 8px; margin-top: 12px; }}
.quote-nav button {{ background: #334155; color: #e2e8f0; border: none; border-radius: 6px; padding: 6px 14px; cursor: pointer; font-size: 13px; }}
.quote-nav button:hover {{ background: #475569; }}
.theme-bar {{ display: flex; align-items: center; margin-bottom: 6px; }}
.theme-bar .label {{ width: 200px; font-size: 13px; color: #94a3b8; }}
.theme-bar .bar {{ height: 20px; background: #3b82f6; border-radius: 4px; min-width: 4px; transition: width 0.3s; }}
.theme-bar .count {{ margin-left: 8px; font-size: 13px; color: #64748b; }}
.full-width {{ grid-column: 1 / -1; }}
</style>
</head>
<body>

<div class="header">
  <h1>RTT Community Sentiment Analysis Dashboard</h1>
  <p>Alternative Data — Facebook Community Discourse on Rett Syndrome Gene Therapies</p>
</div>

<div class="stat-row" id="stats"></div>

<div class="filters">
  <label>Filter by Theme:</label>
  <select id="themeFilter"><option value="all">All Themes</option></select>
  <label>Therapy Mention:</label>
  <select id="therapyFilter">
    <option value="all">All</option>
    <option value="NGNE">NGNE only</option>
    <option value="TSHA">TSHA only</option>
    <option value="both">Both</option>
    <option value="neither">Neither</option>
  </select>
  <label>Sentiment:</label>
  <select id="sentimentFilter">
    <option value="all">All</option>
    <option value="positive">Positive</option>
    <option value="negative">Negative</option>
    <option value="neutral">Neutral</option>
  </select>
</div>

<div class="grid">
  <div class="card">
    <h2>Sentiment: NGNE vs TSHA</h2>
    <canvas id="sentimentChart"></canvas>
  </div>
  <div class="card">
    <h2>Implied Lean Distribution</h2>
    <canvas id="leanChart"></canvas>
  </div>
  <div class="card">
    <h2>Post Activity Timeline</h2>
    <canvas id="timelineChart"></canvas>
  </div>
  <div class="card">
    <h2>Theme Frequency</h2>
    <div id="themeHeatmap"></div>
  </div>
  <div class="card full-width">
    <h2>Notable Quotes</h2>
    <div id="quoteCarousel"></div>
    <div class="quote-nav">
      <button onclick="prevQuote()">&larr; Previous</button>
      <button onclick="nextQuote()">Next &rarr;</button>
      <span id="quoteCounter" style="color:#64748b;font-size:13px;line-height:32px;margin-left:8px;"></span>
    </div>
  </div>
</div>

<script>
const RAW_DATA = {data_json};

let filteredData = [...RAW_DATA];
let quoteIndex = 0;

// --- Utility ---
function countBy(arr, key) {{
  const counts = {{}};
  arr.forEach(item => {{
    const val = item[key] || 'unknown';
    counts[val] = (counts[val] || 0) + 1;
  }});
  return counts;
}}

function applyFilters() {{
  const theme = document.getElementById('themeFilter').value;
  const therapy = document.getElementById('therapyFilter').value;
  const sentiment = document.getElementById('sentimentFilter').value;

  filteredData = RAW_DATA.filter(c => {{
    if (theme !== 'all' && !(c.themes || []).includes(theme)) return false;
    if (therapy !== 'all' && c.therapy_mention !== therapy) return false;
    if (sentiment !== 'all') {{
      const sn = c.sentiment_toward_NGNE;
      const st = c.sentiment_toward_TSHA;
      if (sn !== sentiment && st !== sentiment) return false;
    }}
    return true;
  }});

  renderAll();
}}

// --- Stats ---
function renderStats() {{
  const total = filteredData.length;
  const ngne = filteredData.filter(c => ['NGNE','both'].includes(c.therapy_mention)).length;
  const tsha = filteredData.filter(c => ['TSHA','both'].includes(c.therapy_mention)).length;
  const notable = filteredData.filter(c => c.notable_quote).length;

  document.getElementById('stats').innerHTML = [
    {{n: total, l: 'Total Comments'}},
    {{n: ngne, l: 'NGNE Mentions'}},
    {{n: tsha, l: 'TSHA Mentions'}},
    {{n: notable, l: 'Notable Quotes'}},
  ].map(s => `<div class="stat"><div class="number">${{s.n}}</div><div class="label">${{s.l}}</div></div>`).join('');
}}

// --- Sentiment Chart ---
let sentChart;
function renderSentiment() {{
  const ctx = document.getElementById('sentimentChart').getContext('2d');
  const labels = ['Positive', 'Negative', 'Neutral', 'Not Mentioned'];
  const ngneData = labels.map(l => filteredData.filter(c => c.sentiment_toward_NGNE === l.toLowerCase().replace(' ','_')).length);
  const tshaData = labels.map(l => filteredData.filter(c => c.sentiment_toward_TSHA === l.toLowerCase().replace(' ','_')).length);

  if (sentChart) sentChart.destroy();
  sentChart = new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels,
      datasets: [
        {{ label: 'NGNE (Neurogene)', data: ngneData, backgroundColor: '#3b82f6' }},
        {{ label: 'TSHA (Taysha)', data: tshaData, backgroundColor: '#10b981' }}
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }},
      scales: {{
        x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }},
        y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }}
      }}
    }}
  }});
}}

// --- Lean Chart ---
let leanPie;
function renderLean() {{
  const ctx = document.getElementById('leanChart').getContext('2d');
  const counts = countBy(filteredData, 'implied_lean');
  const labels = Object.keys(counts);
  const values = Object.values(counts);
  const colors = {{ NGNE: '#3b82f6', TSHA: '#10b981', neither: '#64748b', unclear: '#f59e0b' }};

  if (leanPie) leanPie.destroy();
  leanPie = new Chart(ctx, {{
    type: 'pie',
    data: {{
      labels,
      datasets: [{{ data: values, backgroundColor: labels.map(l => colors[l] || '#94a3b8') }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }}
    }}
  }});
}}

// --- Timeline ---
let timeChart;
function renderTimeline() {{
  const ctx = document.getElementById('timelineChart').getContext('2d');
  const dateCounts = {{}};
  filteredData.forEach(c => {{
    const d = (c.date || 'Unknown').substring(0, 7); // group by month
    dateCounts[d] = (dateCounts[d] || 0) + 1;
  }});
  const sorted = Object.entries(dateCounts).sort((a,b) => a[0].localeCompare(b[0]));

  if (timeChart) timeChart.destroy();
  timeChart = new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: sorted.map(s => s[0]),
      datasets: [{{ label: 'Comments', data: sorted.map(s => s[1]), borderColor: '#3b82f6', fill: false, tension: 0.3 }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }},
      scales: {{
        x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }},
        y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }}
      }}
    }}
  }});
}}

// --- Theme Heatmap ---
function renderThemes() {{
  const themeCounts = {{}};
  filteredData.forEach(c => {{
    (c.themes || []).forEach(t => {{ themeCounts[t] = (themeCounts[t] || 0) + 1; }});
  }});
  const sorted = Object.entries(themeCounts).sort((a,b) => b[1] - a[1]);
  const maxCount = sorted.length ? sorted[0][1] : 1;

  document.getElementById('themeHeatmap').innerHTML = sorted.map(([theme, count]) => {{
    const pct = (count / maxCount * 100).toFixed(0);
    return `<div class="theme-bar">
      <div class="label">${{theme.replace(/_/g, ' ')}}</div>
      <div class="bar" style="width:${{pct}}%"></div>
      <div class="count">${{count}}</div>
    </div>`;
  }}).join('');
}}

// --- Quotes ---
function getNotableQuotes() {{
  return filteredData.filter(c => c.notable_quote && (c.verbatim_quote || c.text));
}}

function renderQuote() {{
  const quotes = getNotableQuotes();
  const el = document.getElementById('quoteCarousel');
  const counter = document.getElementById('quoteCounter');
  if (!quotes.length) {{
    el.innerHTML = '<div class="quote-card"><div class="quote-text">No notable quotes match current filters.</div></div>';
    counter.textContent = '';
    return;
  }}
  if (quoteIndex >= quotes.length) quoteIndex = 0;
  if (quoteIndex < 0) quoteIndex = quotes.length - 1;
  const q = quotes[quoteIndex];
  el.innerHTML = `<div class="quote-card">
    <div class="quote-text">"${{(q.verbatim_quote || q.text || '').replace(/"/g, '&quot;')}}"</div>
    <div class="quote-meta">&mdash; ${{q.author_anon || 'Unknown'}} | Lean: ${{q.implied_lean || '?'}} | Themes: ${{(q.themes || []).join(', ')}}</div>
  </div>`;
  counter.textContent = `${{quoteIndex + 1}} / ${{quotes.length}}`;
}}
function nextQuote() {{ quoteIndex++; renderQuote(); }}
function prevQuote() {{ quoteIndex--; renderQuote(); }}

// --- Init ---
function populateThemeFilter() {{
  const themes = new Set();
  RAW_DATA.forEach(c => (c.themes || []).forEach(t => themes.add(t)));
  const sel = document.getElementById('themeFilter');
  [...themes].sort().forEach(t => {{
    const opt = document.createElement('option');
    opt.value = t; opt.textContent = t.replace(/_/g, ' ');
    sel.appendChild(opt);
  }});
}}

function renderAll() {{
  renderStats();
  renderSentiment();
  renderLean();
  renderTimeline();
  renderThemes();
  quoteIndex = 0;
  renderQuote();
}}

document.getElementById('themeFilter').addEventListener('change', applyFilters);
document.getElementById('therapyFilter').addEventListener('change', applyFilters);
document.getElementById('sentimentFilter').addEventListener('change', applyFilters);

populateThemeFilter();
renderAll();
</script>
</body>
</html>"""

    dashboard_file = OUTPUT_DIR / "dashboard.html"
    with open(dashboard_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {dashboard_file}")


if __name__ == "__main__":
    generate_dashboard()
