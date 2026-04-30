"""
Daily intelligence brief generator.
Calls Claude with web search, merges output into template.html, writes index.html.
Run by GitHub Actions on a daily schedule.
"""

import os
import re
import sys
from datetime import datetime, timezone, timedelta

import anthropic

# Brisbane is UTC+10 (no daylight saving)
BRISBANE_TZ = timezone(timedelta(hours=10))


PROMPT = """Search the web for today's news, then produce HTML fragments for an intelligence brief. The fragments will be inserted into a pre-styled template. Use ONLY the CSS classes listed below.

CONTENT REQUIREMENTS:
- Morning panel: section headers for Global Headlines, Australia/Brisbane, Sport, Brisbane Weather, Market Indicators, Global Instability Heat Map. 5-7 cards plus the special components.
- US Politics panel: Trump activity, legal/scandal, Republican dynamics, Democrat actions, midterm developments. 5-7 cards plus a polling box and gauges.
- World panel: geopolitical, diplomatic, economic, science/tech sections. 5-7 cards.
- Middle East panel: battlefield, regional actors, escalation, oil/shipping sections. 5-7 cards plus casualty grid and shipping panel.

AVAILABLE CSS CLASSES:

Section header: <div class="sec-head"><div class="sec-dot" style="background:var(--morning)"></div><div class="sec-title">TITLE</div></div>
Use var(--morning), var(--uspol), var(--world), or var(--mideast) matching the panel.

Card: <div class="card morning"><div class="card-header"><div class="card-left"><span class="card-tag tag-morning">TAG</span><div class="card-title">Title</div><div class="card-preview">Preview 1-2 sentences.</div></div><div class="card-chevron">v</div></div><div class="card-body">Body 3-4 sentences.</div></div>
Replace 'morning' with 'uspol', 'world', or 'mideast' to match panel. Tag classes: tag-morning, tag-uspol, tag-world, tag-mideast, tag-breaking.

Market: <div class="ticker-grid"><div class="tick-cell"><div class="tick-name">Brent Crude</div><div class="tick-val">$112.10</div><div class="tick-chg chg-up">+3.2%</div></div></div>

Weather: <div class="weather-box"><div class="weather-icon">cloud</div><div><div class="weather-temp">26C</div><div class="weather-desc">Partly Cloudy</div><div class="weather-detail">Low 16C 60% humidity</div></div></div>

Sport: <div class="sport-row"><span class="sport-icon">ball</span><div><div class="sport-text">Match</div><div class="sport-sub">Detail</div></div></div>

Heat map: <div class="heatmap"><div class="heat-cell heat-crit"><div class="heat-name">Region</div><div class="heat-lvl">red dot</div><div class="heat-label">CRITICAL</div></div></div>
Classes: heat-crit, heat-high, heat-med, heat-low.

Gauge: <div class="gauge-wrap"><div class="gauge-title">TITLE</div><div class="gauge-row"><div class="gauge-label">Label</div><div class="gauge-bar"><div class="gauge-fill fill-red" style="width:72%"></div></div><div class="gauge-pct">72%</div></div></div>
Fill classes: fill-red, fill-amber, fill-green, fill-blue, fill-purple.

Casualty: <div class="casualty-grid"><div class="cas-cell"><div class="cas-label">LABEL</div><div class="cas-val cas-red">1234</div><div class="cas-sub">sub</div></div></div>
Classes: cas-red, cas-orange, cas-amber, cas-blue.

Shipping: <div class="ship-grid"><div class="ship-row"><div><div class="ship-name">Name</div><div class="ship-detail">Detail</div></div><div class="ship-badge badge-closed">CLOSED</div></div></div>
Badges: badge-closed, badge-partial, badge-open, badge-watch.

Polling: <div class="poll-box"><div class="poll-title">TITLE</div><div class="poll-row"><div class="poll-party" style="color:#3b82f6">Democrats</div><div class="poll-bar"><div class="poll-fill fill-dem" style="width:52%"><span class="poll-pct">45%</span></div></div></div><div class="poll-note">Source</div></div>

Info box: <div class="info-box">Text with <b>bold</b>.</div>

Header pills: <div class="pill pill-red">RISK: HIGH</div><div class="pill pill-amber">STABILITY: LOW</div><div class="pill pill-amber">CONF: MEDIUM</div>
Use pill-red, pill-amber, or pill-green based on assessment.

OUTPUT FORMAT - this is critical:

Return six blocks. Each block is wrapped between its own unique opening and closing markers, on their own lines, with the HTML between. No commentary, no explanation, no markdown fences. Just six blocks back to back like this:

===PILLS_START===
<div class="pill pill-red">...</div>...
===PILLS_END===
===MORNING_START===
<div class="sec-head">...</div><div class="card morning">...</div>...
===MORNING_END===
===USPOL_START===
...HTML...
===USPOL_END===
===WORLD_START===
...HTML...
===WORLD_END===
===MIDEAST_START===
...HTML...
===MIDEAST_END===

No other text before, between, or after the blocks."""


def call_claude():
    """Call Claude with web search enabled and return the full text response."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=16000,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 8,
        }],
        messages=[{"role": "user", "content": PROMPT}],
    )
    
    # Concatenate all text blocks from the response
    text_parts = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
    
    full_text = "".join(text_parts)
    print(f"Claude returned {len(full_text)} characters, stop_reason={response.stop_reason}")
    return full_text


def extract_block(text, name):
    """Pull HTML out of a ===NAME_START=== ... ===NAME_END=== block."""
    pattern = rf"==={name}_START==={{0,1}}\s*([\s\S]*?)\s*==={name}_END==="
    # Cleaner regex
    pattern = rf"==={name}_START===\s*([\s\S]*?)\s*==={name}_END==="
    match = re.search(pattern, text)
    if not match:
        raise RuntimeError(f"Could not find {name} block in Claude's response")
    return match.group(1).strip()


def build_brief(claude_text, template):
    """Replace template tokens with content from Claude and timestamps."""
    now = datetime.now(BRISBANE_TZ)
    header_meta = now.strftime("%a %d %b %Y · %H:%M") + " AEST"
    footer_timestamp = now.strftime("%d %b %Y · %H:%M") + " AEST"
    
    pills = extract_block(claude_text, "PILLS")
    morning = extract_block(claude_text, "MORNING")
    uspol = extract_block(claude_text, "USPOL")
    world = extract_block(claude_text, "WORLD")
    mideast = extract_block(claude_text, "MIDEAST")
    
    output = template
    output = output.replace("{{HEADER_META}}", header_meta)
    output = output.replace("{{HEADER_PILLS}}", pills)
    output = output.replace("{{MORNING_CONTENT}}", morning)
    output = output.replace("{{USPOL_CONTENT}}", uspol)
    output = output.replace("{{WORLD_CONTENT}}", world)
    output = output.replace("{{MIDEAST_CONTENT}}", mideast)
    output = output.replace("{{FOOTER_TIMESTAMP}}", footer_timestamp)
    
    return output


def main():
    print("Reading template...")
    with open("template.html", "r", encoding="utf-8") as f:
        template = f.read()
    
    print("Calling Claude...")
    claude_text = call_claude()
    
    print("Building brief...")
    brief_html = build_brief(claude_text, template)
    
    print(f"Writing index.html ({len(brief_html)} characters)...")
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(brief_html)
    
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
