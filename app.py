"""viact.ai Webpage Content Agent — 3-Agent Market Radar Pipeline"""
import os
import sys
import json

import streamlit as st

# ── Load secrets ──────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ[_k] = _v
except Exception:
    pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="viact.ai Webpage Agent",
    page_icon="🏗️",
    layout="wide",
)

# ── viAct Dark Theme ──────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Jost:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Jost', sans-serif !important; }

/* Hide Streamlit Branding */
#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}

/* Background and Sidebar Colors */
.stApp { background-color: #080a0f; }
[data-testid="stSidebar"] { background-color: #0d1117 !important; border-right: 1px solid #1f2430; }

/* Body text */
p, li, span, label, div { color: #c9d1d9; }
h1, h2, h3, h4 { color: #e6edf3 !important; }
.stMarkdown p { color: #c9d1d9; }

/* Custom Inputs and Text Areas */
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div {
    background-color: rgba(18,21,28,0.8) !important;
    border: 1px solid #2d303a !important;
    border-radius: 8px !important;
}
textarea, input { color: #e6edf3 !important; background-color: transparent !important; }

/* Input Focus Glow */
div[data-baseweb="input"] > div:focus-within {
    border-color: #ff6a3d !important;
    box-shadow: 0 0 12px rgba(255,106,61,0.4) !important;
}

/* Primary Button Gradient */
button[kind="primary"] {
    background: linear-gradient(135deg,#ff6a3d 0%,#e54d1f 100%) !important;
    color: white !important; border: none !important;
    border-radius: 8px !important; font-weight: 600 !important;
    font-size: 1.05rem !important; transition: all 0.3s ease !important;
    padding: 0.6rem 1.4rem !important;
}
button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(255,106,61,0.45) !important;
}

/* Secondary Button */
button[kind="secondary"] {
    background: rgba(22,25,33,0.8) !important;
    color: #ff6a3d !important; border: 1px solid #ff6a3d !important;
    border-radius: 8px !important; font-weight: 600 !important;
}

/* Glassmorphism Card Style */
.glass-card {
    background: rgba(22,25,33,0.7); backdrop-filter: blur(15px);
    border: 1px solid rgba(255,106,61,0.15); border-radius: 12px;
    padding: 25px; position: relative; overflow: hidden;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2); transition: all 0.3s ease;
    margin-bottom: 16px;
}
.glass-card:hover {
    border-color: rgba(255,106,61,0.35);
    box-shadow: 0 12px 40px rgba(255,106,61,0.1);
}

/* Metric Typography */
.metric-title { color: #8b949e; font-size: 0.82rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 6px; }
.metric-value { color: #ff6a3d; font-size: 2.4rem; font-weight: 700; line-height: 1.1; margin-bottom: 6px; }

/* Custom Tabs Styling */
div[data-baseweb="tab-list"] { gap: 8px; margin-bottom: 20px; background: transparent !important; border: none !important; }
div[data-baseweb="tab"] {
    background-color: rgba(22,25,33,0.8) !important; border-radius: 6px !important;
    padding: 10px 18px !important; border: 1px solid #2d303a !important;
    color: #8b949e !important; font-weight: 600 !important; font-size: 0.92rem !important;
}
div[aria-selected="true"] {
    background-color: #ff6a3d !important; color: white !important;
    border-color: #ff6a3d !important; box-shadow: 0 4px 15px rgba(255,106,61,0.4) !important;
}

/* Status Badges */
.badge-confirmed { background: #0d4429; color: #3fb950; padding: 3px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; border: 1px solid #238636; display: inline-block; }
.badge-high { background: rgba(255,106,61,0.15); color: #ff6a3d; padding: 3px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; border: 1px solid rgba(255,106,61,0.4); display: inline-block; }
.badge-medium { background: rgba(210,153,34,0.15); color: #d6a126; padding: 3px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; border: 1px solid rgba(210,153,34,0.4); display: inline-block; }
.badge-low { background: rgba(200,60,60,0.15); color: #f85149; padding: 3px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; border: 1px solid rgba(200,60,60,0.4); display: inline-block; }

/* Step indicator */
.step-active { background: linear-gradient(135deg,#ff6a3d,#e54d1f); color: white; padding: 10px 18px; border-radius: 8px; text-align: center; font-weight: 600; font-size: 0.88rem; }
.step-done { background: rgba(63,185,80,0.12); color: #3fb950; padding: 10px 18px; border-radius: 8px; text-align: center; font-weight: 600; font-size: 0.88rem; border: 1px solid #238636; }
.step-idle { background: rgba(22,25,33,0.6); color: #484f58; padding: 10px 18px; border-radius: 8px; text-align: center; font-weight: 600; font-size: 0.88rem; border: 1px solid #2d303a; }

/* Alert / Info boxes */
div[data-testid="stAlert"] { border-radius: 8px !important; border-left-width: 3px !important; }

/* Divider */
hr { border-color: #2d303a !important; }

/* Expander */
details { background: rgba(22,25,33,0.6) !important; border: 1px solid #2d303a !important; border-radius: 8px !important; }
summary { color: #c9d1d9 !important; font-weight: 600 !important; }

/* Code blocks */
code { background: rgba(22,25,33,0.8) !important; color: #ff6a3d !important; border: 1px solid #2d303a !important; border-radius: 4px !important; padding: 2px 6px !important; }
pre code { color: #c9d1d9 !important; }

/* Radio buttons */
div[data-testid="stRadio"] label { color: #c9d1d9 !important; }

/* Log box */
.log-box {
    background: #0d1117; border: 1px solid #2d303a; border-radius: 8px;
    padding: 14px 16px; font-family: 'Courier New', monospace; font-size: 0.78rem;
    color: #58a6ff; line-height: 1.6; max-height: 260px; overflow-y: auto;
}

/* Caption / small text */
small, .caption { color: #8b949e !important; font-size: 0.82rem !important; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="glass-card" style="padding:2rem 2.5rem; margin-bottom:1.5rem; border-color: rgba(255,106,61,0.25);">
    <div style="display:flex; align-items:center; gap:1rem;">
        <span style="font-size:2.6rem;">🏗️</span>
        <div>
            <h1 style="margin:0; font-size:1.9rem; color:#e6edf3; font-weight:700;">viact.ai Webpage Content Agent</h1>
            <p style="margin:0.3rem 0 0 0; color:#8b949e; font-size:0.9rem;">
                <span style="color:#ff6a3d; font-weight:600;">Agent 1</span> Tavily Market Radar
                &nbsp;·&nbsp;
                <span style="color:#ff6a3d; font-weight:600;">Agent 2</span> Firecrawl Scraping
                &nbsp;·&nbsp;
                <span style="color:#ff6a3d; font-weight:600;">Agent 3</span> Groq/Llama Content Generation
            </p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# 3-AGENT MARKET RADAR → WEBPAGE PIPELINE (Tavily + Firecrawl + Groq)
# =============================================================================

if "r3_step" not in st.session_state:
    st.session_state["r3_step"] = 0

step = st.session_state["r3_step"]

# ── Step indicator ─────────────────────────────────────────────────────────────
steps = ["📡  Market Radar", "🎯  Topic Selection", "✅  Content Suite"]
cols = st.columns(3)
for i, (col, label) in enumerate(zip(cols, steps)):
    if i < step:
        css_class = "step-done"
        prefix = "✓ "
    elif i == step:
        css_class = "step-active"
        prefix = ""
    else:
        css_class = "step-idle"
        prefix = ""
    col.markdown(
        f"<div class='{css_class}'>{prefix}{label}</div>",
        unsafe_allow_html=True,
    )

if step > 0:
    st.write("")
    if st.button("↩ Start Over", key="r3_reset"):
        for k in [k for k in st.session_state if k.startswith("r3_")]:
            del st.session_state[k]
        st.rerun()

st.write("")

# =============================================================================
# STEP 0 — API Key Check + Run Market Radar
# =============================================================================
if step == 0:
    st.markdown("""
<div class="glass-card">
    <h3 style="margin:0 0 0.6rem 0; color:#e6edf3;">📡 How the 3-Agent Pipeline Works</h3>
    <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; margin-top:12px;">
        <div style="background:rgba(255,106,61,0.07); border:1px solid rgba(255,106,61,0.2); border-radius:8px; padding:14px;">
            <div style="color:#ff6a3d; font-weight:700; font-size:0.85rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px;">Agent 1 — Tavily</div>
            <div style="color:#c9d1d9; font-size:0.88rem;">Searches competitors, confirms gaps via <code>site:viact.ai</code> — only 0-result topics are real gaps.</div>
        </div>
        <div style="background:rgba(255,106,61,0.07); border:1px solid rgba(255,106,61,0.2); border-radius:8px; padding:14px;">
            <div style="color:#ff6a3d; font-weight:700; font-size:0.85rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px;">Agent 2 — Firecrawl</div>
            <div style="color:#c9d1d9; font-size:0.88rem;">Scrapes competitor pages using anti-bot bypass. Returns clean Markdown for Agent 3 to use.</div>
        </div>
        <div style="background:rgba(255,106,61,0.07); border:1px solid rgba(255,106,61,0.2); border-radius:8px; padding:14px;">
            <div style="color:#ff6a3d; font-weight:700; font-size:0.85rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px;">Agent 3 — Groq/Llama</div>
            <div style="color:#c9d1d9; font-size:0.88rem;">Generates content using ONLY real scraped data. Zero-hallucination contract enforced at prompt level.</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

    st.write("")

    # ── API Key Status ─────────────────────────────────────────────────────────
    st.markdown("<p style='color:#8b949e; font-size:0.82rem; font-weight:700; text-transform:uppercase; letter-spacing:1.5px; margin-bottom:10px;'>API KEY STATUS</p>", unsafe_allow_html=True)

    key_configs = [
        ("GROQ_API_KEY",      "Groq",      "LLM — Llama 3.3 70B",   "Agent 3"),
        ("TAVILY_API_KEY",    "Tavily",    "Live Search API",        "Agent 1"),
        ("FIRECRAWL_API_KEY", "Firecrawl", "Anti-Bot Scraper",       "Agent 2"),
    ]

    key_cols = st.columns(3)
    all_required_present = True
    for col, (key_name, label, desc, agent) in zip(key_cols, key_configs):
        val = os.getenv(key_name, "")
        present = bool(val)
        if key_name != "FIRECRAWL_API_KEY" and not present:
            all_required_present = False
        status_color = "#3fb950" if present else "#f85149"
        status_icon = "●" if present else "○"
        masked = f"{val[:8]}…" if present else "Not set"
        col.markdown(f"""
<div class="glass-card" style="padding:16px;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <span style="color:#e6edf3; font-weight:700; font-size:0.95rem;">{label}</span>
        <span style="color:{status_color}; font-size:1.2rem;">{status_icon}</span>
    </div>
    <div style="color:#8b949e; font-size:0.78rem;">{desc} · <span style="color:#ff6a3d;">{agent}</span></div>
    <div style="color:{status_color}; font-size:0.78rem; margin-top:4px; font-family: monospace;">{masked}</div>
</div>
""", unsafe_allow_html=True)

    if not all_required_present:
        st.markdown("""
<div style="background:rgba(248,81,73,0.08); border:1px solid rgba(248,81,73,0.3); border-radius:8px; padding:12px 16px; font-size:0.85rem; color:#f85149; margin-bottom:12px;">
    ⚠️ Add missing keys to <code>.env</code>: &nbsp;<code>GROQ_API_KEY=gsk_...</code> &nbsp;·&nbsp; <code>TAVILY_API_KEY=tvly-...</code>
</div>
""", unsafe_allow_html=True)

    st.write("")
    run_radar = st.button(
        "🚀  Run Market Radar",
        type="primary",
        use_container_width=False,
        key="r3_run",
        disabled=not all_required_present,
    )

    if run_radar:
        from agent1_market_explorer import discover_market_gaps

        st.markdown("<hr/>", unsafe_allow_html=True)
        status_box = st.empty()
        log_lines: list[str] = []

        def _ui_progress(phase: str, message: str):
            log_lines.append(message)
            status_box.markdown(
                "<div class='log-box'>" + "<br>".join(log_lines[-16:]) + "</div>",
                unsafe_allow_html=True,
            )

        with st.spinner("Agent 1 running Tavily searches and confirming gaps..."):
            try:
                radar_results = discover_market_gaps(progress_callback=_ui_progress)
                if not radar_results.get("topics"):
                    st.warning("No confirmed gaps found. Try again or check your Tavily API key.")
                else:
                    st.session_state["r3_results"] = radar_results
                    st.session_state["r3_step"] = 1
                    st.rerun()
            except Exception as e:
                st.error(f"Agent 1 failed: {e}")

# =============================================================================
# STEP 1 — Confirmed Gap Cards + HITL Topic Selection
# =============================================================================
elif step == 1:
    radar = st.session_state["r3_results"]
    topics = radar.get("topics", [])
    scan_ts = radar.get("scan_timestamp", "")
    n_scanned = radar.get("total_competitors_scanned", 0)

    st.markdown(f"""
<div style="display:flex; align-items:center; gap:16px; margin-bottom:20px;">
    <h3 style="margin:0; color:#e6edf3;">🎯 Confirmed Content Gaps</h3>
    <div style="background:rgba(255,106,61,0.1); border:1px solid rgba(255,106,61,0.3); border-radius:20px; padding:4px 14px; font-size:0.8rem; color:#ff6a3d; font-weight:600;">
        {n_scanned} competitors scanned · {scan_ts}
    </div>
</div>
""", unsafe_allow_html=True)

    # ── Render topic cards ─────────────────────────────────────────────────────
    for i, topic in enumerate(topics):
        opp = topic.get("opportunity_score", "?")
        opp_class = {"High": "badge-high", "Medium": "badge-medium", "Low": "badge-low"}.get(opp, "badge-medium")
        comp_count = topic.get("competitor_count", 0)
        evidence = topic.get("competitor_evidence", [])

        evidence_rows = "".join(
            f"<tr style='border-bottom:1px solid #2d303a;'>"
            f"<td style='padding:6px 10px; color:#ff6a3d; font-weight:600; font-size:0.8rem; white-space:nowrap;'>{e.get('competitor','')}</td>"
            f"<td style='padding:6px 10px; font-size:0.78rem;'><a href='{e.get('url','')}' target='_blank' style='color:#58a6ff; text-decoration:none;'>{e.get('url','')[:55]}…</a></td>"
            f"<td style='padding:6px 10px; color:#8b949e; font-size:0.76rem;'>{e.get('snippet','')[:90]}…</td>"
            f"</tr>"
            for e in evidence[:4]
        )

        st.markdown(f"""
<div class="glass-card">
    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
        <div>
            <div style="color:#8b949e; font-size:0.75rem; font-weight:700; text-transform:uppercase; letter-spacing:1.2px; margin-bottom:4px;">Gap {i+1}</div>
            <h4 style="margin:0; color:#e6edf3; font-size:1.1rem; font-weight:700;">{topic['topic']}</h4>
        </div>
        <div style="display:flex; gap:8px; flex-shrink:0; margin-left:16px;">
            <span class="badge-confirmed">✅ CONFIRMED GAP</span>
            <span class="{opp_class}">{opp} Opportunity</span>
        </div>
    </div>

    <div style="background:rgba(255,106,61,0.06); border:1px solid rgba(255,106,61,0.15); border-radius:6px; padding:8px 12px; margin-bottom:14px; font-size:0.8rem; color:#8b949e; font-family:monospace;">
        {topic.get('viact_search_query', '')} → <span style="color:#3fb950; font-weight:700;">0 dedicated solution pages</span> · confirmed {topic.get('confirmed_at', '')}
    </div>

    <div style="display:grid; grid-template-columns:1fr 2fr; gap:20px;">
        <div>
            <div style="color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px;">Why Trending</div>
            <div style="color:#c9d1d9; font-size:0.87rem;">{topic.get('why_trending', '')}</div>
        </div>
        <div>
            <div style="color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">Competitor Evidence ({comp_count} competitor{'s' if comp_count != 1 else ''})</div>
            {"<table style='width:100%; border-collapse:collapse;'><thead><tr style='background:rgba(255,255,255,0.03);'><th style='padding:6px 10px; color:#8b949e; font-size:0.78rem; text-align:left;'>Competitor</th><th style='padding:6px 10px; color:#8b949e; font-size:0.78rem; text-align:left;'>URL</th><th style='padding:6px 10px; color:#8b949e; font-size:0.78rem; text-align:left;'>Snippet</th></tr></thead><tbody>" + evidence_rows + "</tbody></table>" if evidence else "<div style='color:#484f58; font-size:0.82rem;'>Gap confirmed via Tavily search — no direct snippet evidence collected.</div>"}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

    # ── HITL Gate ──────────────────────────────────────────────────────────────
    st.markdown("<hr/>", unsafe_allow_html=True)
    st.markdown("<h3 style='color:#e6edf3; margin-bottom:16px;'>Which gap should we build a page for?</h3>", unsafe_allow_html=True)

    topic_options = [f"Gap {i+1}: {t['topic']}" for i, t in enumerate(topics)]
    selected_option = st.radio(
        "Select a gap:",
        topic_options,
        key="r3_topic_choice",
        label_visibility="collapsed",
    )
    selected_idx = topic_options.index(selected_option)

    st.write("")
    st.markdown("""
<div style="margin-bottom:6px;">
    <span style="color:#e6edf3; font-weight:600;">Reference material</span>
    <span style="color:#8b949e; font-size:0.82rem; margin-left:8px;">— optional but recommended</span>
</div>
<div style="color:#8b949e; font-size:0.82rem; margin-bottom:8px;">
    Paste MOM/BCA report excerpts, viAct case study data, or reference URLs.
    Leave blank to use public regulatory data <span style="color:#d6a126;">(output marked [Unverified])</span>.
</div>
""", unsafe_allow_html=True)

    references = st.text_area(
        "Reference material",
        placeholder=(
            "e.g. MOM WSH Report 2024: falls from height = 35% of fatalities\n"
            "viAct Marina Bay project: 0 incidents in 18 months\n"
            "Or leave blank and click proceed"
        ),
        height=120,
        key="r3_refs_input",
        label_visibility="collapsed",
    )

    firecrawl_available = bool(os.getenv("FIRECRAWL_API_KEY"))

    if not firecrawl_available:
        st.markdown("""
<div style="background:rgba(210,153,34,0.08); border:1px solid rgba(210,153,34,0.3); border-radius:8px; padding:10px 14px; font-size:0.83rem; color:#d6a126; margin:10px 0;">
    ⚠️ <code>FIRECRAWL_API_KEY</code> not set — Agent 2 will skip scraping. Agent 3 will use Tavily snippets only.
</div>
""", unsafe_allow_html=True)

    st.write("")
    if st.button(
        f"⚡  Extract Data & Generate Content Suite — Gap {selected_idx + 1}",
        type="primary",
        key="r3_generate",
    ):
        raw_refs = references.strip()
        selected_topic = topics[selected_idx]

        st.session_state["r3_selected_idx"] = selected_idx
        st.session_state["r3_references"] = raw_refs
        st.session_state["r3_unverified"] = not bool(raw_refs)

        # ── Agent 2: Firecrawl scrape ──────────────────────────────────────────
        competitor_urls = [
            e["url"] for e in selected_topic.get("competitor_evidence", []) if e.get("url")
        ]

        competitor_data: dict = {}
        if firecrawl_available and competitor_urls:
            from agent2_data_extractor import extract_competitor_content

            a2_status = st.empty()
            a2_log: list[str] = []

            def _a2_cb(phase: str, message: str):
                a2_log.append(message)
                a2_status.markdown(
                    "<div class='log-box'>" + "<br>".join(a2_log[-8:]) + "</div>",
                    unsafe_allow_html=True,
                )

            with st.spinner("Agent 2: Firecrawl scraping competitor pages..."):
                try:
                    competitor_data = extract_competitor_content(
                        competitor_urls, progress_callback=_a2_cb
                    )
                except Exception as exc:
                    st.warning(f"Agent 2 failed: {exc} — proceeding with Tavily snippets only.")
        else:
            for url in competitor_urls:
                competitor_data[url] = {
                    "success": False,
                    "markdown": "[ACCESS DENIED]",
                    "word_count": 0,
                    "error": "Firecrawl key not configured",
                }

        st.session_state["r3_competitor_data"] = competitor_data

        # ── Agent 3: Content generation ────────────────────────────────────────
        viact_pages = radar.get("viact_known_pages", [])

        with st.spinner("Agent 3: Generating structured content suite (Llama 3.3 70B)..."):
            try:
                from agent3_content_architect import generate_structured_content, build_webpage_body

                content = generate_structured_content(
                    topic=selected_topic["topic"],
                    competitor_data=competitor_data,
                    viact_pages=viact_pages,
                    references=raw_refs,
                    radar_topic_entry=selected_topic,
                )

                if not content.get("webpage_body"):
                    content["webpage_body"] = build_webpage_body(content)

                st.session_state["r3_content"] = content
                st.session_state["r3_step"] = 2
                st.rerun()
            except Exception as e:
                st.error(f"Agent 3 failed: {e}")

# =============================================================================
# STEP 2 — Content Preview + Push to Sheets
# =============================================================================
elif step == 2:
    radar = st.session_state["r3_results"]
    selected_idx = st.session_state["r3_selected_idx"]
    references = st.session_state.get("r3_references", "")
    unverified = st.session_state.get("r3_unverified", True)
    competitor_data = st.session_state.get("r3_competitor_data", {})
    selected_topic = radar["topics"][selected_idx]
    topic_str = selected_topic["topic"]
    content = st.session_state["r3_content"]

    # ── Header ─────────────────────────────────────────────────────────────────
    st.markdown(f"""
<div class="glass-card" style="border-color:rgba(63,185,80,0.25);">
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:{'10px' if unverified else '0'};">
        <span style="font-size:1.6rem;">✅</span>
        <div>
            <div style="color:#8b949e; font-size:0.75rem; font-weight:700; text-transform:uppercase; letter-spacing:1.2px;">Content Suite Ready</div>
            <h3 style="margin:2px 0 0 0; color:#e6edf3;">{topic_str}</h3>
        </div>
    </div>
    {"<div style='margin-top:10px; background:rgba(210,153,34,0.08); border:1px solid rgba(210,153,34,0.25); border-radius:6px; padding:8px 12px; font-size:0.82rem; color:#d6a126;'>⚠️ <strong>[Unverified]</strong> — No reference material provided. Statistics use public MOM/BCA data. Add a reference source before publishing.</div>" if unverified else ""}
</div>
""", unsafe_allow_html=True)

    # ── Push to Sheets ─────────────────────────────────────────────────────────
    col_push, _ = st.columns([1, 4])
    with col_push:
        if st.button("📊  Push to Google Sheets", type="primary", key="r3_push"):
            try:
                from push_to_sheets import push_webpage
                competitor_urls_list = list(competitor_data.keys())
                push_webpage(
                    content=content,
                    decision_logic=content.get("decision_logic", ""),
                    input_source=f"3-Agent Radar — {radar.get('scan_timestamp', '')}",
                    competitor_urls=competitor_urls_list,
                    unverified=unverified,
                )
                sheet_url = f"https://docs.google.com/spreadsheets/d/{os.getenv('SHEET_ID', '')}"
                st.success(f"✅ Row written to 'Webpage Content' tab — [Open Sheet ↗]({sheet_url})")
            except Exception as e:
                st.error(f"Sheets error: {e}")

    st.markdown("<hr/>", unsafe_allow_html=True)

    # ── Content Preview Tabs ───────────────────────────────────────────────────
    (
        tab_dl, tab_sources, tab_body, tab_seo,
        tab_faqs, tab_schema, tab_geo,
        tab_visual, tab_links, tab_raw
    ) = st.tabs([
        "📋 Decision Logic",
        "🔍 Data Sources",
        "📄 Webpage Body",
        "🔎 SEO Suite",
        "❓ FAQs",
        "🏷️ Schema JSON-LD",
        "🌐 GEO Package",
        "📷 Visual Strategy",
        "🔗 Internal Links",
        "🔧 Raw JSON",
    ])

    with tab_dl:
        st.markdown("""
<div style="background:rgba(88,166,255,0.07); border:1px solid rgba(88,166,255,0.2); border-radius:8px; padding:10px 14px; font-size:0.84rem; color:#58a6ff; margin-bottom:14px;">
    💡 Copy this paragraph into Gary / Surendra's email. It cites the exact Tavily search, date, and real competitor URLs.
</div>
""", unsafe_allow_html=True)
        st.text_area(
            "Decision Logic",
            content.get("decision_logic", ""),
            height=220,
            key="r3_dl_text",
        )

    with tab_sources:
        st.markdown("<h4 style='color:#e6edf3;'>Agent 1 — Tavily Gap Confirmation</h4>", unsafe_allow_html=True)
        st.markdown(f"""
<div class="glass-card" style="padding:16px;">
    <div style="margin-bottom:8px;"><span style="color:#8b949e; font-size:0.8rem;">Search:</span> <code>{selected_topic.get('viact_search_query', '')}</code> → <span style="color:#3fb950; font-weight:700;">0 dedicated solution pages</span></div>
    <div style="margin-bottom:8px;"><span style="color:#8b949e; font-size:0.8rem;">Confirmed:</span> <span style="color:#c9d1d9;">{selected_topic.get('confirmed_at', '')}</span></div>
    <div><span style="color:#8b949e; font-size:0.8rem;">Opportunity:</span> <span style="color:#ff6a3d; font-weight:700;">{selected_topic.get('opportunity_score', '?')}</span> &nbsp;·&nbsp; <span style="color:#8b949e; font-size:0.8rem;">{selected_topic.get('competitor_count', 0)} competitors covering this topic</span></div>
</div>
""", unsafe_allow_html=True)

        evidence = selected_topic.get("competitor_evidence", [])
        if evidence:
            st.markdown("<div style='color:#e6edf3; font-weight:600; margin:12px 0 8px;'>Competitor snippets:</div>", unsafe_allow_html=True)
            for e in evidence:
                with st.expander(f"{e.get('competitor', '')} — {e.get('url', '')}"):
                    st.write(e.get("snippet", ""))

        st.markdown("<hr/><h4 style='color:#e6edf3;'>Agent 2 — Firecrawl Scrape Results</h4>", unsafe_allow_html=True)
        if competitor_data:
            for url, result in competitor_data.items():
                if result.get("success"):
                    st.markdown(f"<div style='color:#3fb950; font-size:0.84rem; margin-bottom:4px;'>✅ <code>{url[:65]}</code> — {result.get('word_count', 0)} words scraped</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='color:#f85149; font-size:0.84rem; margin-bottom:4px;'>🚫 <code>{url[:65]}</code> — ACCESS DENIED ({result.get('error', 'unknown')})</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='color:#484f58; font-size:0.84rem;'>No competitor URLs were scraped.</div>", unsafe_allow_html=True)

        used = content.get("data_sources_used", [])
        denied = content.get("access_denied_urls", [])
        if used:
            st.markdown(f"<div style='margin-top:12px; color:#8b949e; font-size:0.82rem;'>Agent 3 used: {', '.join(used[:4])}</div>", unsafe_allow_html=True)
        if denied:
            st.markdown(f"<div style='color:#f85149; font-size:0.82rem;'>Agent 3 skipped (ACCESS DENIED): {', '.join(denied[:4])}</div>", unsafe_allow_html=True)

    with tab_body:
        body = content.get("webpage_body", "")
        st.text_area("Webpage Body (Markdown — paste into CMS)", body, height=520, key="r3_body_text")
        with st.expander("👁️ Preview rendered page"):
            st.markdown(body)

    with tab_seo:
        seo = content.get("seo_suite", {})
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("<div style='color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;'>Meta</div>", unsafe_allow_html=True)
            st.text_input("Meta Title", seo.get("meta_title", ""), key="r3_meta_title")
            st.caption(f"{len(seo.get('meta_title', ''))} chars — target 50-60")
            st.text_area("Meta Description", seo.get("meta_description", ""), height=90, key="r3_meta_desc")
            st.caption(f"{len(seo.get('meta_description', ''))} chars — target 140-155")
            st.text_input("Canonical Slug", seo.get("canonical_url_slug", ""), key="r3_slug")
        with c2:
            st.markdown("<div style='color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:12px;'>Keywords</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='margin-bottom:8px;'><span style='color:#8b949e; font-size:0.82rem;'>Primary: </span><code>{seo.get('primary_keyword', '')}</code></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='margin-bottom:8px; color:#8b949e; font-size:0.82rem;'>Secondary: " + " &nbsp;·&nbsp; ".join(f"<code>{k}</code>" for k in seo.get("secondary_keywords", [])) + "</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='margin-bottom:12px; color:#8b949e; font-size:0.82rem;'>LSI: " + " &nbsp;·&nbsp; ".join(f"<code>{k}</code>" for k in seo.get("lsi_keywords", [])) + "</div>", unsafe_allow_html=True)
            st.markdown("<div style='color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;'>Heading Map</div>", unsafe_allow_html=True)
            for h in seo.get("heading_map", []):
                depth = 1 if h.startswith("H1") else (2 if h.startswith("H2") else 3)
                indent = (depth - 1) * 14
                st.markdown(f"<div style='margin-left:{indent}px; color:#c9d1d9; font-size:0.84rem; margin-bottom:4px;'>{'─' * (depth-1)} {h}</div>", unsafe_allow_html=True)

    with tab_faqs:
        st.markdown("<div style='color:#e6edf3; font-weight:700; margin-bottom:12px;'>Schema FAQs <span style='color:#8b949e; font-size:0.82rem; font-weight:400;'>— 5 items · 40-60 word answers · used in JSON-LD</span></div>", unsafe_allow_html=True)
        for i, faq in enumerate(content.get("schema_faqs", []), 1):
            with st.expander(f"Q{i}: {faq.get('question', '')}"):
                st.write(faq.get("answer", ""))
                st.caption(f"{len(faq.get('answer','').split())} words")
        st.markdown("<hr/><div style='color:#e6edf3; font-weight:700; margin:12px 0;'>Extended FAQs <span style='color:#8b949e; font-size:0.82rem; font-weight:400;'>— 2 items · 80-120 word answers · on-page only</span></div>", unsafe_allow_html=True)
        for i, faq in enumerate(content.get("extended_faqs", []), 1):
            with st.expander(f"Extended Q{i}: {faq.get('question', '')}"):
                st.write(faq.get("answer", ""))
                st.caption(f"{len(faq.get('answer','').split())} words")

    with tab_schema:
        st.markdown("""
<div style="background:rgba(88,166,255,0.07); border:1px solid rgba(88,166,255,0.2); border-radius:8px; padding:10px 14px; font-size:0.84rem; color:#58a6ff; margin-bottom:14px;">
    Paste into <code>&lt;head&gt;</code> as <code>&lt;script type="application/ld+json"&gt;{ ... }&lt;/script&gt;</code>. Contains the 5 Schema FAQs only.
</div>
""", unsafe_allow_html=True)
        st.code(content.get("schema_json_ld", ""), language="json")

    with tab_geo:
        geo = content.get("geo_package", {})
        st.markdown("""
<div style="background:rgba(88,166,255,0.07); border:1px solid rgba(88,166,255,0.2); border-radius:8px; padding:10px 14px; font-size:0.84rem; color:#58a6ff; margin-bottom:14px;">
    💡 Written to be cited by Claude, Perplexity, ChatGPT, and Google AI Overviews.
</div>
""", unsafe_allow_html=True)
        st.markdown("<div style='color:#e6edf3; font-weight:600; margin-bottom:8px;'>Opening 200 Words — AI-citation optimized:</div>", unsafe_allow_html=True)
        st.text_area("Opening 200 words", geo.get("opening_200_words", ""), height=180, key="r3_geo")
        st.markdown("<div style='color:#e6edf3; font-weight:600; margin:14px 0 8px;'>Citation Framing Tips:</div>", unsafe_allow_html=True)
        for tip in geo.get("citation_framing_tips", []):
            st.markdown(f"<div style='background:rgba(22,25,33,0.6); border:1px solid #2d303a; border-radius:6px; padding:8px 12px; margin-bottom:6px; color:#c9d1d9; font-size:0.85rem;'>→ {tip}</div>", unsafe_allow_html=True)

    with tab_visual:
        prompts = content.get("nano_banana_prompts", content.get("visual_strategy", []))
        st.markdown("<div style='color:#8b949e; font-size:0.82rem; margin-bottom:12px;'>Realistic photography, APAC context, human-centered — not CGI. For use with Nano Banana 2.</div>", unsafe_allow_html=True)
        for i, v in enumerate(prompts, 1):
            with st.expander(f"Image {i} — {v.get('placement', '')}"):
                st.text_area(f"Prompt {i}", v.get("prompt", ""), height=140, key=f"r3_vis_{i}")
                st.markdown(f"<div style='color:#8b949e; font-size:0.82rem; margin-top:6px;'><strong style='color:#e6edf3;'>Alt text:</strong> {v.get('alt_text', '')}</div>", unsafe_allow_html=True)

    with tab_links:
        st.markdown("<div style='color:#e6edf3; font-weight:600; margin-bottom:10px;'>Internal Links — verified viAct.ai URLs only:</div>", unsafe_allow_html=True)
        for link in content.get("internal_links", []):
            url_val = link.get("url", "")
            st.markdown(
                f"<div style='background:rgba(22,25,33,0.6); border:1px solid #2d303a; border-radius:6px; padding:10px 14px; margin-bottom:8px;'>"
                f"<div style='color:#ff6a3d; font-weight:600; font-size:0.88rem;'>{link.get('anchor_text', '')}</div>"
                f"<div style='margin:4px 0;'><a href='{url_val}' target='_blank' style='color:#58a6ff; font-size:0.82rem;'>{url_val}</a></div>"
                f"<div style='color:#8b949e; font-size:0.8rem;'>{link.get('context', '')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    with tab_raw:
        st.json(content)
