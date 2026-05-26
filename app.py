"""viact.ai Webpage Content Agent — 3-Agent Market Radar Pipeline"""
import os
import sys
import json
import html as _html_lib

import streamlit as st


def _t(text: str) -> str:
    """Sanitize dynamic text for HTML embedding — escapes HTML chars, strips newlines."""
    return _html_lib.escape(str(text)).replace('\n', ' ').replace('\r', '')


def _html(s: str) -> str:
    """Collapse a multi-line HTML string to a single line so CommonMark never treats
    indented lines as code blocks and blank lines never break HTML block mode."""
    return " ".join(part.strip() for part in s.splitlines() if part.strip())

# ── Load secrets (localhost: .env  |  Streamlit Cloud: st.secrets) ───────────
# override=True ensures an updated .env is picked up without restarting the process
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except Exception:
    pass

# Streamlit Cloud fallback: if a key wasn't set by .env (cloud has no .env),
# pull from st.secrets.  Locally, .env wins because load_dotenv already set it.
_SECRET_KEYS = [
    "GROQ_API_KEY", "TAVILY_API_KEY", "FIRECRAWL_API_KEY",
    "SHEET_ID", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
    "GCP_SERVICE_ACCOUNT",
]
for _k in _SECRET_KEYS:
    try:
        if not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
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

/* Pipeline flow boxes */
.pipeline-box {
    background: rgba(22,25,33,0.8); border: 1px solid rgba(255,106,61,0.2);
    border-radius: 10px; padding: 18px 16px; flex: 1; min-width: 0;
}
.pipeline-arrow {
    color: #ff6a3d; font-size: 1.5rem; align-self: center;
    flex-shrink: 0; padding: 0 6px; opacity: 0.7;
}
.pipeline-tag {
    background: rgba(255,106,61,0.12); color: #ff6a3d;
    border: 1px solid rgba(255,106,61,0.3); border-radius: 4px;
    padding: 2px 8px; font-size: 0.72rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1px; display: inline-block; margin-bottom: 8px;
}
.pipeline-output {
    background: rgba(63,185,80,0.06); border: 1px solid rgba(63,185,80,0.2);
    border-radius: 4px; padding: 5px 10px; margin-top: 10px;
    font-size: 0.78rem; color: #3fb950;
}

/* Output chips (what you'll get) */
.output-chip {
    background: rgba(22,25,33,0.7); border: 1px solid #2d303a;
    border-radius: 8px; padding: 12px 14px;
}
.output-chip-icon { font-size: 1.3rem; margin-bottom: 5px; }
.output-chip-title { color: #e6edf3; font-weight: 700; font-size: 0.85rem; margin-bottom: 3px; }
.output-chip-desc { color: #8b949e; font-size: 0.76rem; line-height: 1.4; }

/* Step indicator with sub-label */
.step-wrap { text-align: center; }
.step-num-active { background: linear-gradient(135deg,#ff6a3d,#e54d1f); color: white; width: 32px; height: 32px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.9rem; margin-bottom: 6px; }
.step-num-done { background: rgba(63,185,80,0.15); color: #3fb950; width: 32px; height: 32px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.9rem; margin-bottom: 6px; border: 1px solid #238636; }
.step-num-idle { background: rgba(22,25,33,0.5); color: #484f58; width: 32px; height: 32px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.9rem; margin-bottom: 6px; border: 1px solid #2d303a; }
.step-title-active { color: #e6edf3; font-weight: 700; font-size: 0.9rem; }
.step-title-done { color: #3fb950; font-weight: 700; font-size: 0.9rem; }
.step-title-idle { color: #484f58; font-weight: 600; font-size: 0.9rem; }
.step-sub { color: #8b949e; font-size: 0.76rem; margin-top: 3px; }
.step-connector { color: #2d303a; font-size: 1.2rem; align-self: flex-start; padding-top: 14px; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(_html("""
<div class="glass-card" style="padding:1.8rem 2rem; margin-bottom:1.2rem; border-color:rgba(255,106,61,0.3);">
<div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:16px;">
<div>
<div style="color:#ff6a3d; font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:2px; margin-bottom:6px;">viAct &middot; Content Intelligence</div>
<h1 style="margin:0; font-size:1.85rem; color:#e6edf3; font-weight:700; line-height:1.2;">Webpage Content Agent</h1>
<p style="margin:8px 0 0; color:#8b949e; font-size:0.92rem; max-width:520px; line-height:1.5;">Finds topics your competitors rank for that <strong style="color:#e6edf3;">viAct doesn't have yet</strong> &#8212; then writes a complete, publish-ready webpage in under 3 minutes.</p>
</div>
<div style="display:flex; gap:8px; flex-wrap:wrap;">
<span style="background:rgba(255,106,61,0.1); color:#ff6a3d; border:1px solid rgba(255,106,61,0.3); border-radius:6px; padding:5px 10px; font-size:0.75rem; font-weight:700;">&#128225; Tavily Search</span>
<span style="background:rgba(255,106,61,0.1); color:#ff6a3d; border:1px solid rgba(255,106,61,0.3); border-radius:6px; padding:5px 10px; font-size:0.75rem; font-weight:700;">&#128293; Firecrawl Scrape</span>
<span style="background:rgba(255,106,61,0.1); color:#ff6a3d; border:1px solid rgba(255,106,61,0.3); border-radius:6px; padding:5px 10px; font-size:0.75rem; font-weight:700;">&#129302; Llama 3.3 70B</span>
</div>
</div>
</div>
"""), unsafe_allow_html=True)

# =============================================================================
# =============================================================================
# TABS — Market Radar  |  Industry Pages
# =============================================================================
tab_radar, tab_industry = st.tabs([
    "📡 Market Radar — Find Content Gaps",
    "🏭 Industry Pages — Full Landing Pages",
])

with tab_radar:
    # 3-AGENT MARKET RADAR → WEBPAGE PIPELINE (Tavily + Firecrawl + Groq)
    # =============================================================================

    if "r3_step" not in st.session_state:
        st.session_state["r3_step"] = 0

    step = st.session_state["r3_step"]

    # ── Step indicator ────────────────────────────────────────────────────────────
    _step_data = [
        ("1", "Competitor Research",   "Scan 8 sites · find content gaps"),
        ("2", "Pick Your Topic",       "Choose gap · add reference material"),
        ("3", "Content Ready",         "Review 10 sections · push to Sheets"),
    ]
    _si_cols = st.columns([1, 0.08, 1, 0.08, 1])
    _col_idxs = [0, 2, 4]
    for _si, ((_num, _title, _sub), _ci) in enumerate(zip(_step_data, _col_idxs)):
        if _si < step:
            _num_cls, _title_cls, _check = "step-num-done", "step-title-done", "&#10003;"
        elif _si == step:
            _num_cls, _title_cls, _check = "step-num-active", "step-title-active", _num
        else:
            _num_cls, _title_cls, _check = "step-num-idle", "step-title-idle", _num
        _si_cols[_ci].markdown(_html(f"""
    <div class="step-wrap">
    <div class="{_num_cls}">{_check}</div>
    <div class="{_title_cls}">{_title}</div>
    <div class="step-sub">{_sub}</div>
    </div>
    """), unsafe_allow_html=True)
        if _ci < 4:
            _si_cols[_ci + 1].markdown(
                f"<div style='text-align:center; color:#2d303a; font-size:1.4rem; padding-top:8px;'>&#8594;</div>",
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
        # ── Pipeline flow diagram ──────────────────────────────────────────────────
        st.markdown(
            "<p style='color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1.8px; margin-bottom:12px;'>HOW IT WORKS &mdash; 3 AI AGENTS IN SEQUENCE</p>",
            unsafe_allow_html=True,
        )
        st.markdown(_html("""
    <div style="display:flex; gap:0; align-items:stretch; margin-bottom:20px;">

    <div class="pipeline-box" style="border-color:rgba(255,106,61,0.35);">
    <div class="pipeline-tag">Agent 1 &middot; Tavily Search</div>
    <div style="color:#e6edf3; font-weight:700; font-size:1rem; margin-bottom:6px;">&#128269; Find the Gap</div>
    <div style="color:#8b949e; font-size:0.82rem; line-height:1.6;">
    &#8226; Searches <strong style="color:#c9d1d9;">8 competitor websites</strong> for safety topics<br>
    &#8226; AI extracts 10&ndash;15 topic names from results<br>
    &#8226; Checks each topic on <code>viact.ai</code> &#8212; live<br>
    &#8226; Only topics with <strong style="color:#3fb950;">0 viAct pages</strong> pass through
    </div>
    <div class="pipeline-output">&#8594; Output: 3 Confirmed Content Gaps</div>
    </div>

    <div class="pipeline-arrow">&#9654;</div>

    <div class="pipeline-box" style="border-color:rgba(88,166,255,0.3);">
    <div class="pipeline-tag" style="background:rgba(88,166,255,0.1); color:#58a6ff; border-color:rgba(88,166,255,0.3);">Agent 2 &middot; Firecrawl</div>
    <div style="color:#e6edf3; font-weight:700; font-size:1rem; margin-bottom:6px;">&#128196; Read Competitor Pages</div>
    <div style="color:#8b949e; font-size:0.82rem; line-height:1.6;">
    &#8226; Downloads full competitor page content<br>
    &#8226; Bypasses anti-bot protection automatically<br>
    &#8226; Converts messy HTML to clean text<br>
    &#8226; Blocked pages marked <strong style="color:#f85149;">[ACCESS DENIED]</strong> &#8212; never faked
    </div>
    <div class="pipeline-output" style="border-color:rgba(88,166,255,0.2); color:#58a6ff;">&#8594; Output: Real Competitor Markdown</div>
    </div>

    <div class="pipeline-arrow">&#9654;</div>

    <div class="pipeline-box" style="border-color:rgba(63,185,80,0.3);">
    <div class="pipeline-tag" style="background:rgba(63,185,80,0.08); color:#3fb950; border-color:rgba(63,185,80,0.3);">Agent 3 &middot; Llama 3.3 70B</div>
    <div style="color:#e6edf3; font-weight:700; font-size:1rem; margin-bottom:6px;">&#9999; Write the Webpage</div>
    <div style="color:#8b949e; font-size:0.82rem; line-height:1.6;">
    &#8226; Uses <strong style="color:#c9d1d9;">only</strong> the scraped content &#8212; zero hallucination<br>
    &#8226; Writes headline, body, FAQs, meta tags<br>
    &#8226; Adds Singapore &amp; UAE regulatory context<br>
    &#8226; Generates schema markup + image prompts
    </div>
    <div class="pipeline-output" style="border-color:rgba(63,185,80,0.2); color:#3fb950;">&#8594; Output: 10-Section Publish-Ready Page</div>
    </div>

    </div>
    """), unsafe_allow_html=True)

        # ── What you'll get ────────────────────────────────────────────────────────
        st.markdown(
            "<p style='color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1.8px; margin-bottom:12px;'>WHAT YOU GET &mdash; 10 SECTIONS, READY TO PUBLISH</p>",
            unsafe_allow_html=True,
        )
        _outputs = [
            ("&#128196;", "Full Webpage Body",    "Complete Markdown page — paste into any CMS"),
            ("&#127919;", "H1 Headline",          "Problem-focused, no marketing fluff"),
            ("&#128269;", "SEO Meta Tags",        "Title &lt;60 chars, description &lt;155 chars"),
            ("&#10067;",  "5 Schema FAQs",        "40-60 word answers for Google rich results"),
            ("&#127991;", "JSON-LD Schema",       "Paste-ready &lt;script&gt; for structured data"),
            ("&#127760;", "GEO Package",          "Opening 200 words for ChatGPT/Perplexity citations"),
            ("&#128247;", "2 Image Prompts",      "Realistic APAC photography briefs, not CGI"),
            ("&#128279;", "Internal Links",       "Verified viact.ai URLs only — never invented"),
            ("&#128202;", "Decision Logic",       "Email paragraph with proof for Gary/Surendra"),
            ("&#128220;", "Keyword Set",          "Primary + LSI keywords + heading map"),
        ]
        _out_cols = st.columns(5)
        for _oi, (_icon, _title, _desc) in enumerate(_outputs):
            _out_cols[_oi % 5].markdown(_html(f"""
    <div class="output-chip">
    <div class="output-chip-icon">{_icon}</div>
    <div class="output-chip-title">{_title}</div>
    <div class="output-chip-desc">{_desc}</div>
    </div>
    """), unsafe_allow_html=True)

        st.write("")

        # ── Competitor grid (static — no API calls) ────────────────────────────────
        from research_competitors import get_all_competitors
        _all_competitors = get_all_competitors()

        st.markdown(_html(f"""
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:10px;">
    <p style="margin:0; color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1.8px;">
    COMPETITOR WEBSITES AGENT 1 WILL SCAN &nbsp;<span style="color:#ff6a3d;">({len(_all_competitors)} sites)</span>
    </p>
    <span style="color:#8b949e; font-size:0.76rem;">All searched simultaneously via Tavily</span>
    </div>
    """), unsafe_allow_html=True)
        _comp_cols = st.columns(4)
        for _ci, _comp in enumerate(_all_competitors):
            _domain = _comp["url"].split("//")[-1].split("/")[0]
            _comp_cols[_ci % 4].markdown(
                _html(f"""
    <div class="glass-card" style="padding:12px 14px;">
    <div style="color:#e6edf3; font-weight:700; font-size:0.88rem; margin-bottom:3px;">{_t(_comp['name'])}</div>
    <div style="color:#8b949e; font-size:0.74rem; font-family:monospace;">{_t(_domain)}</div>
    </div>
    """), unsafe_allow_html=True)

        st.write("")

        # ── API Key Status ─────────────────────────────────────────────────────────
        st.markdown(_html("""
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:10px;">
    <p style="margin:0; color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1.8px;">API CONNECTIONS</p>
    <span style="color:#8b949e; font-size:0.76rem;">All 3 agents need their own API key to work</span>
    </div>
    """), unsafe_allow_html=True)

        key_configs = [
            ("TAVILY_API_KEY",    "Tavily",    "&#128269;", "Searches competitor websites &amp; confirms gaps on viact.ai",  "Agent 1 — Required", True),
            ("FIRECRAWL_API_KEY", "Firecrawl", "&#128293;", "Downloads full competitor page content bypassing anti-bot",     "Agent 2 — Optional", False),
            ("GROQ_API_KEY",      "Groq",      "&#129302;", "Runs Llama 3.3 70B to extract topics and write page content",   "Agent 1 &amp; 3 — Required", True),
        ]

        key_cols = st.columns(3)
        all_required_present = True
        for col, (key_name, label, icon, desc, agent_label, required) in zip(key_cols, key_configs):
            val = os.getenv(key_name, "")
            present = bool(val)
            if required and not present:
                all_required_present = False
            status_color = "#3fb950" if present else ("#f85149" if required else "#d6a126")
            status_text  = "Connected" if present else ("Missing" if required else "Optional")
            masked = f"{val[:8]}…" if present else "Not set"
            col.markdown(_html(f"""
    <div class="glass-card" style="padding:16px; border-color:rgba({'63,185,80' if present else ('248,81,73' if required else '210,153,34')},0.25);">
    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
    <div style="display:flex; align-items:center; gap:8px;">
    <span style="font-size:1.3rem;">{icon}</span>
    <span style="color:#e6edf3; font-weight:700; font-size:0.98rem;">{_t(label)}</span>
    </div>
    <span style="background:rgba({'63,185,80' if present else ('248,81,73' if required else '210,153,34')},0.1); color:{status_color}; border:1px solid rgba({'63,185,80' if present else ('248,81,73' if required else '210,153,34')},0.3); border-radius:20px; padding:2px 8px; font-size:0.72rem; font-weight:700;">{status_text}</span>
    </div>
    <div style="color:#8b949e; font-size:0.78rem; line-height:1.5; margin-bottom:6px;">{desc}</div>
    <div style="display:flex; justify-content:space-between; align-items:center;">
    <span style="color:#ff6a3d; font-size:0.72rem; font-weight:600;">{agent_label}</span>
    <span style="color:{status_color}; font-size:0.74rem; font-family:monospace;">{_t(masked)}</span>
    </div>
    </div>
    """), unsafe_allow_html=True)

        if not all_required_present:
            st.markdown(_html("""
    <div style="background:rgba(248,81,73,0.06); border:1px solid rgba(248,81,73,0.3); border-radius:8px; padding:12px 16px; font-size:0.84rem; color:#f85149; margin-bottom:4px;">
    <strong>&#9888; Missing required API keys.</strong> Add them to your <code>.env</code> file or Streamlit Cloud secrets:
    <br><code style="color:#c9d1d9;">GROQ_API_KEY=gsk_...</code> &nbsp;&middot;&nbsp; <code style="color:#c9d1d9;">TAVILY_API_KEY=tvly-...</code>
    </div>
    """), unsafe_allow_html=True)

        st.write("")

        # ── Industry Vertical Selector ─────────────────────────────────────────────
        INDUSTRY_OPTIONS = {
            "Construction Safety":     "construction safety",
            "Oil & Gas Safety":        "oil gas safety",
            "Manufacturing Safety":    "manufacturing safety",
            "Mining Safety":           "mining safety",
            "Facility Management":     "facility management safety",
            "Food & Beverage Safety":  "food beverage safety",
        }
        _ind_label = st.selectbox(
            "🏭  Industry Vertical — which sector should Agent 1 search?",
            options=list(INDUSTRY_OPTIONS.keys()),
            index=0,
            key="r3_industry_label",
            help="Agent 1 will search competitor sites using this industry keyword.",
        )
        st.session_state["r3_industry"] = INDUSTRY_OPTIONS[_ind_label]

        st.markdown(_html("""
    <div style="background:rgba(255,106,61,0.04); border:1px solid rgba(255,106,61,0.15); border-radius:8px; padding:12px 16px; margin-bottom:12px; display:flex; align-items:center; gap:12px;">
    <span style="font-size:1.4rem;">&#9201;</span>
    <div>
    <div style="color:#e6edf3; font-weight:600; font-size:0.88rem;">Takes about 2&ndash;3 minutes</div>
    <div style="color:#8b949e; font-size:0.78rem;">Agent 1 runs ~12 live searches (8 competitors + 10-15 viact.ai checks). No action needed &mdash; just watch the progress below.</div>
    </div>
    </div>
    """), unsafe_allow_html=True)
        run_radar = st.button(
            "🚀  Run Market Radar  —  Find What Competitors Are Winning",
            type="primary",
            use_container_width=True,
            key="r3_run",
            disabled=not all_required_present,
        )

        if run_radar:
            from agent1_market_explorer import discover_market_gaps

            st.markdown("<hr/>", unsafe_allow_html=True)

            # ── Pre-flight: quick Tavily key validation ────────────────────────────
            _tavily_key = os.getenv("TAVILY_API_KEY", "")
            _tavily_ok = False
            try:
                import requests as _rq
                _r = _rq.post("https://api.tavily.com/search", json={
                    "api_key": _tavily_key, "query": "test", "max_results": 1
                }, timeout=12)
                _tavily_ok = _r.status_code == 200
                if not _tavily_ok:
                    _err_body = _r.json() if _r.headers.get("content-type","").startswith("application/json") else {}
                    _err_msg = _err_body.get("message") or _err_body.get("detail") or f"HTTP {_r.status_code}"
                    st.error(
                        f"**Tavily API key failed** ({_err_msg}).  "
                        f"Key in use: `{_tavily_key[:20]}...`  \n\n"
                        "**Fix:** Get a new free key at [tavily.com](https://tavily.com) "
                        "and update it in `.env` (local) or Streamlit Cloud → Settings → Secrets."
                    )
            except Exception as _te:
                st.error(f"Tavily connection error: {_te}")

            if not _tavily_ok:
                st.stop()

            # ── 3-phase progress panel (reset on every new run) ───────────────────
            st.session_state["r3_progress"] = {"competitors": [], "topics": [], "gaps": [], "logs": []}

            progress_placeholder = st.empty()

            def _render_progress():
                prog = st.session_state["r3_progress"]
                comp_items  = prog["competitors"]   # "Name|N" strings
                topic_items = prog["topics"]         # plain topic name strings
                gap_items   = prog["gaps"]           # "CONFIRMED|name|score" or "SKIP|name|url"
                log_items   = prog.get("logs", [])   # general agent1 messages

                n_comp  = len(comp_items)
                n_topic = len(topic_items)
                n_confirmed = sum(1 for g in gap_items if g.startswith("CONFIRMED"))
                n_gap   = len(gap_items)

                # Phase A rows
                comp_rows = "".join(
                    f"<div style='display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid #1f2430;'>"
                    f"<span style='color:#c9d1d9; font-size:0.82rem;'>{_t(item.split('|')[0])}</span>"
                    f"<span style='color:#8b949e; font-size:0.78rem;'>{_t(item.split('|')[1])} snippet(s)</span>"
                    f"</div>"
                    for item in comp_items
                )

                # Phase B rows
                topic_rows = "".join(
                    f"<div style='padding:3px 0; color:#c9d1d9; font-size:0.82rem; border-bottom:1px solid #1f2430;'>&#8250; {_t(t)}</div>"
                    for t in topic_items
                )

                # Phase C rows
                gap_rows = "".join(
                    (
                        f"<div style='padding:4px 0; border-bottom:1px solid #1f2430;'>"
                        f"<span style='background:rgba(255,106,61,0.12); color:#ff6a3d; border:1px solid rgba(255,106,61,0.3); border-radius:4px; padding:1px 7px; font-size:0.74rem; font-weight:700; margin-right:6px;'>&#10003; CONFIRMED</span>"
                        f"<span style='color:#e6edf3; font-size:0.82rem;'>{_t(parts[1] if len(parts) > 1 else '')}</span>"
                        f"<span style='color:#ff6a3d; font-size:0.74rem; margin-left:6px;'>{_t(parts[2] if len(parts) > 2 else '')}</span>"
                        f"</div>"
                        if g.startswith("CONFIRMED") else
                        f"<div style='padding:4px 0; border-bottom:1px solid #1f2430;'>"
                        f"<span style='color:#484f58; font-size:0.78rem; margin-right:6px;'>&#8627; skip</span>"
                        f"<span style='color:#484f58; font-size:0.8rem;'>{_t(parts[1] if len(parts) > 1 else '')}</span>"
                        f"</div>"
                    )
                    for g in gap_items
                    for parts in [g.split("|")]
                )

                html_out = (
                    f"<div style='background:#0d1117; border:1px solid #2d303a; border-radius:10px; overflow:hidden; margin-top:8px;'>"

                    # Phase A header
                    f"<div style='padding:10px 14px; background:rgba(255,106,61,0.06); border-bottom:1px solid #2d303a; display:flex; justify-content:space-between;'>"
                    f"<span style='color:#ff6a3d; font-weight:700; font-size:0.82rem; text-transform:uppercase; letter-spacing:1px;'>&#128225; Competitors Scanned</span>"
                    f"<span style='color:#8b949e; font-size:0.8rem;'>{n_comp} / {len(_all_competitors)}</span>"
                    f"</div>"
                    + (f"<div style='padding:8px 14px;'>{comp_rows}</div>" if comp_rows else "")

                    # Phase B header
                    + f"<div style='padding:10px 14px; background:rgba(88,166,255,0.05); border-top:1px solid #2d303a; border-bottom:1px solid #2d303a; display:flex; justify-content:space-between;'>"
                    f"<span style='color:#58a6ff; font-weight:700; font-size:0.82rem; text-transform:uppercase; letter-spacing:1px;'>&#128269; Topics Extracted</span>"
                    f"<span style='color:#8b949e; font-size:0.8rem;'>{n_topic} topic(s)</span>"
                    f"</div>"
                    + (f"<div style='padding:8px 14px;'>{topic_rows}</div>" if topic_rows else "")

                    # Phase C header
                    + f"<div style='padding:10px 14px; background:rgba(63,185,80,0.05); border-top:1px solid #2d303a; border-bottom:1px solid #2d303a; display:flex; justify-content:space-between;'>"
                    f"<span style='color:#3fb950; font-weight:700; font-size:0.82rem; text-transform:uppercase; letter-spacing:1px;'>&#10003; Gap Confirmation</span>"
                    f"<span style='color:#8b949e; font-size:0.8rem;'>{n_confirmed} confirmed &middot; {n_gap} checked of {n_topic}</span>"
                    f"</div>"
                    + (f"<div style='padding:8px 14px;'>{gap_rows}</div>" if gap_rows else "")

                    # Log panel — shows errors, dedup notices, viact.ai check details
                    + (
                        f"<div style='padding:10px 14px; background:rgba(139,148,158,0.04); border-top:1px solid #2d303a;'>"
                        f"<div style='color:#8b949e; font-size:0.74rem; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px;'>Agent Log</div>"
                        + "".join(
                            f"<div style='padding:2px 0; color:{'#f85149' if any(w in m.lower() for w in ('failed','error','warn','missing')) else '#484f58'}; font-size:0.76rem; font-family:monospace;'>{_t(m)}</div>"
                            for m in log_items[-20:]
                        )
                        + "</div>"
                        if log_items else ""
                    )

                    + "</div>"
                )
                progress_placeholder.markdown(html_out, unsafe_allow_html=True)

            def _ui_progress(phase: str, message: str):
                if phase in ("competitors", "topics", "gaps"):
                    st.session_state["r3_progress"][phase].append(message)
                else:
                    # agent1 general log — capture errors, dedup notices, etc.
                    st.session_state["r3_progress"]["logs"].append(message)
                _render_progress()

            with st.spinner("Agent 1 running Tavily searches and confirming gaps..."):
                try:
                    radar_results = discover_market_gaps(
                        progress_callback=_ui_progress,
                        industry=st.session_state.get("r3_industry", "construction safety"),
                    )
                    if not radar_results.get("topics"):
                        _logs = st.session_state.get("r3_progress", {}).get("logs", [])
                        _last_logs = "  \n".join(f"`{m}`" for m in _logs[-5:]) if _logs else ""
                        st.warning(
                            "**No confirmed gaps found this run.**  \n"
                            "Possible reasons: all topics are already covered by viact.ai, "
                            "topics were recently generated (12-week dedup), or all competitor "
                            "searches returned low-signal results.  \n\n"
                            + (f"**Last agent messages:**  \n{_last_logs}  \n\n" if _last_logs else "")
                            + "Try a different **Industry Vertical** or click **Run again**."
                        )
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

        st.markdown(_html(f"""
    <div style="margin-bottom:16px;">
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:6px;">
    <h3 style="margin:0; color:#e6edf3;">&#127919; These Topics Competitors Cover — viAct Does Not</h3>
    <span style="background:rgba(255,106,61,0.1); border:1px solid rgba(255,106,61,0.3); border-radius:20px; padding:3px 12px; font-size:0.78rem; color:#ff6a3d; font-weight:600;">{_t(n_scanned)} sites scanned &middot; {_t(scan_ts)}</span>
    </div>
    <p style="margin:0; color:#8b949e; font-size:0.84rem;">Each gap below was <strong style="color:#3fb950;">live-verified</strong> by searching viact.ai &#8212; only topics with zero existing pages are shown. Pick one to build a webpage for.</p>
    </div>
    """), unsafe_allow_html=True)

        # ── Render topic cards ─────────────────────────────────────────────────────
        for i, topic in enumerate(topics):
            opp = topic.get("opportunity_score", "?")
            opp_class = {"High": "badge-high", "Medium": "badge-medium", "Low": "badge-low"}.get(opp, "badge-medium")
            comp_count = topic.get("competitor_count", 0)
            evidence = topic.get("competitor_evidence", [])

            evidence_rows = "".join(
                "<tr style='border-bottom:1px solid #2d303a;'>"
                f"<td style='padding:6px 10px; color:#ff6a3d; font-weight:600; font-size:0.8rem; white-space:nowrap;'>{_t(e.get('competitor',''))}</td>"
                f"<td style='padding:6px 10px; font-size:0.78rem;'><a href='{_t(e.get('url',''))}' target='_blank' style='color:#58a6ff; text-decoration:none;'>{_t(e.get('url','')[:55])}…</a></td>"
                f"<td style='padding:6px 10px; color:#8b949e; font-size:0.76rem;'>{_t(e.get('snippet','')[:90])}…</td>"
                "</tr>"
                for e in evidence[:4]
            )
            evidence_table = (
                "<table style='width:100%; border-collapse:collapse;'>"
                "<thead><tr style='background:rgba(255,255,255,0.03);'>"
                "<th style='padding:6px 10px; color:#8b949e; font-size:0.78rem; text-align:left;'>Competitor</th>"
                "<th style='padding:6px 10px; color:#8b949e; font-size:0.78rem; text-align:left;'>URL</th>"
                "<th style='padding:6px 10px; color:#8b949e; font-size:0.78rem; text-align:left;'>Snippet</th>"
                "</tr></thead>"
                f"<tbody>{evidence_rows}</tbody></table>"
                if evidence else
                "<div style='color:#484f58; font-size:0.82rem;'>Gap confirmed via Tavily search — no direct snippet evidence collected.</div>"
            )
            plural_s = "s" if comp_count != 1 else ""

            st.markdown(_html(f"""
    <div class="glass-card" style="border-color:rgba(255,106,61,0.2);">
    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px;">
    <div>
    <div style="color:#8b949e; font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:1.5px; margin-bottom:4px;">Content Gap {i+1} of {len(topics)}</div>
    <h4 style="margin:0; color:#e6edf3; font-size:1.15rem; font-weight:700;">{_t(topic['topic'])}</h4>
    </div>
    <div style="display:flex; gap:8px; flex-shrink:0; margin-left:16px;">
    <span class="badge-confirmed">&#10003; viAct Has No Page</span>
    <span class="{opp_class}">{_t(opp)} Opportunity</span>
    </div>
    </div>
    <div style="background:rgba(63,185,80,0.05); border:1px solid rgba(63,185,80,0.2); border-radius:6px; padding:8px 12px; margin-bottom:14px; display:flex; align-items:center; gap:10px;">
    <span style="font-size:1rem;">&#128269;</span>
    <span style="font-size:0.8rem; color:#8b949e;">Tavily searched <code>viact.ai</code> for <strong style="color:#c9d1d9;">&ldquo;{_t(topic['topic'])}&rdquo;</strong> &#8594; <strong style="color:#3fb950;">0 solution pages found</strong> &middot; checked {_t(topic.get('confirmed_at', ''))}</span>
    </div>
    <div style="display:grid; grid-template-columns:1fr 2fr; gap:20px;">
    <div>
    <div style="color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px;">Why Trending</div>
    <div style="color:#c9d1d9; font-size:0.87rem;">{_t(topic.get('why_trending', ''))}</div>
    </div>
    <div>
    <div style="color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">Competitor Evidence ({_t(comp_count)} competitor{plural_s})</div>
    {evidence_table}
    </div>
    </div>
    </div>
    """), unsafe_allow_html=True)

        # ── HITL Gate ──────────────────────────────────────────────────────────────
        st.divider()
        st.subheader("Which gap should we build a page for?")

        topic_options = [f"Gap {i+1}: {t['topic']}" for i, t in enumerate(topics)]
        selected_option = st.selectbox(
            "Select a gap to build a webpage for:",
            topic_options,
            key="r3_topic_choice",
        )
        selected_idx = topic_options.index(selected_option)

        st.write("")

        # ── Reference Library — persistent storage in Google Sheets ───────────────
        with st.expander("📚 Reference Library — auto-loaded in every run (Manual + GitHub Actions)", expanded=False):
            st.caption(
                "Add viAct project stats, case studies, MOM/OSHAD data here ONCE. "
                "Every future pipeline run — including Monday's automated run — will load these automatically."
            )
            _ref_svc = None
            _ref_sheet_id = os.getenv("SHEET_ID", "")
            _lib_rows = []
            try:
                from push_to_sheets import get_sheets_service, read_reference_library, add_reference, ensure_reference_tab
                from googleapiclient.discovery import build as _gsa_build
                _ref_svc = get_sheets_service()
                ensure_reference_tab(_ref_svc, _ref_sheet_id)
                # Load raw rows for display
                _raw = _ref_svc.spreadsheets().values().get(
                    spreadsheetId=_ref_sheet_id,
                    range="Reference_Library!A:D"
                ).execute()
                _lib_rows = _raw.get("values", [])[1:]  # skip header
            except Exception:
                pass

            selected_topic_name = topics[selected_idx]["topic"] if topics else ""

            if _lib_rows:
                st.markdown(f"**{len(_lib_rows)} reference(s) stored** — auto-loaded for every Agent 3 run")
                _display = []
                for r in _lib_rows:
                    _type = r[0] if len(r) > 0 else ""
                    _filter = r[1] if len(r) > 1 else "—"
                    _text = r[2][:80] + "..." if len(r) > 2 and len(r[2]) > 80 else (r[2] if len(r) > 2 else "")
                    _date = r[3] if len(r) > 3 else ""
                    _display.append({"Type": _type, "Topic Filter": _filter or "—", "Text Preview": _text, "Added": _date})
                st.dataframe(_display, use_container_width=True, hide_index=True)
            else:
                st.info("No references stored yet. Add your first one below.")

            st.markdown("**Add a new reference:**")
            _col1, _col2 = st.columns([1, 2])
            with _col1:
                _ref_type = st.selectbox("Type", ["global", "topic"], key="ref_lib_type",
                    help="global = always included  |  topic = only when topic name matches filter")
                _topic_filter = st.text_input("Topic Filter (for topic type)", key="ref_lib_filter",
                    placeholder="e.g. fatigue, permit, confined",
                    help="Leave blank for global. Enter keyword that must appear in the topic name.")
            with _col2:
                _ref_text = st.text_area("Reference Text", key="ref_lib_text", height=100,
                    placeholder=(
                        "e.g. Marina Bay Sands: 0 incidents, 18 months, 2400 workers\n"
                        "MOM WSH 2024: 35% of fatalities from falls\n"
                        "viAct: 90% risk reduction, 400+ sites, $2.5M savings"
                    ))
            if st.button("💾 Save to Reference Library", key="ref_lib_save"):
                if _ref_text.strip() and _ref_svc:
                    try:
                        add_reference(_ref_svc, _ref_sheet_id, _ref_type, _topic_filter.strip(), _ref_text.strip())
                        st.success("Saved! This reference will be loaded in all future runs.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")
                elif not _ref_text.strip():
                    st.warning("Please enter reference text before saving.")
                else:
                    st.warning("Sheets not connected — check SHEET_ID and service account credentials.")

        st.write("")
        st.markdown("**📄 Additional Reference Material** — for this run only (optional)")
        st.caption(
            "Already have a Reference Library above? This is for one-off data specific to this run only. "
            "What to paste: MOM/BCA report stats · viAct project data · regulatory quotes"
        )

        references = st.text_area(
            "Reference material (optional)",
            placeholder=(
                "e.g. MOM WSH Report 2024: falls from height = 35% of fatalities\n"
                "viAct Marina Bay Sands project: 0 incidents across 18 months\n"
                "BCA: construction sector accounts for 28% of workplace fatalities\n"
                "Leave blank — Reference Library entries are loaded automatically"
            ),
            height=100,
            key="r3_refs_input",
        )

        firecrawl_available = bool(os.getenv("FIRECRAWL_API_KEY"))

        if not firecrawl_available:
            st.markdown(_html("""
    <div style="background:rgba(210,153,34,0.06); border:1px solid rgba(210,153,34,0.3); border-radius:8px; padding:10px 14px; font-size:0.82rem; color:#d6a126; margin:10px 0;">
    <strong>&#9888; Firecrawl key not set</strong> &#8212; Agent 2 will skip competitor page scraping. Agent 3 will use only the short Tavily snippets. Content quality will be lower. Add <code>FIRECRAWL_API_KEY</code> for best results.
    </div>
    """), unsafe_allow_html=True)

        st.write("")
        st.markdown(_html("""
    <div style="background:rgba(255,106,61,0.04); border:1px solid rgba(255,106,61,0.15); border-radius:8px; padding:10px 16px; margin-bottom:10px; display:flex; gap:10px; align-items:center;">
    <span style="font-size:1.2rem;">&#9201;</span>
    <div style="color:#8b949e; font-size:0.8rem;">
    <strong style="color:#c9d1d9;">What happens next:</strong> Agent 2 downloads competitor pages (30s) &#8594; Agent 3 writes your full webpage using only that real content (60-90s). Total: ~2 minutes.
    </div>
    </div>
    """), unsafe_allow_html=True)
        if st.button(
            f"⚡  Build Webpage for Gap {selected_idx + 1}: {topics[selected_idx]['topic'][:50]}{'…' if len(topics[selected_idx]['topic']) > 50 else ''}",
            type="primary",
            use_container_width=True,
            key="r3_generate",
        ):
            # Merge: Reference Library (persistent) + manual textarea (this-run only)
            selected_topic = topics[selected_idx]
            _lib_refs = ""
            try:
                from push_to_sheets import get_sheets_service as _gss2, read_reference_library as _rrl
                _svc2 = _gss2()
                _lib_refs = _rrl(_svc2, os.getenv("SHEET_ID", ""), topic=selected_topic["topic"])
            except Exception:
                pass
            manual_refs = references.strip()
            raw_refs = "\n".join(filter(None, [_lib_refs, manual_refs]))

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
        _unverified_banner = "<div style='margin-top:10px; background:rgba(210,153,34,0.06); border:1px solid rgba(210,153,34,0.25); border-radius:6px; padding:8px 12px; font-size:0.82rem; color:#d6a126;'>&#9888; <strong>[Unverified]</strong> &#8212; No reference material was provided. Statistics use public MOM/BCA data only. Add real project data before publishing.</div>" if unverified else ""
        _mb = "10px" if unverified else "0"
        st.markdown(_html(f"""
    <div class="glass-card" style="border-color:rgba(63,185,80,0.3); background:rgba(22,25,33,0.8);">
    <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; margin-bottom:{_mb};">
    <div style="display:flex; align-items:center; gap:12px;">
    <div style="background:rgba(63,185,80,0.15); border:1px solid #238636; border-radius:50%; width:40px; height:40px; display:flex; align-items:center; justify-content:center; font-size:1.2rem; flex-shrink:0;">&#10003;</div>
    <div>
    <div style="color:#3fb950; font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:1.5px; margin-bottom:3px;">10-Section Webpage Ready to Publish</div>
    <h3 style="margin:0; color:#e6edf3; font-size:1.1rem;">{_t(topic_str)}</h3>
    </div>
    </div>
    <div style="display:flex; gap:8px; flex-wrap:wrap;">
    <span style="background:rgba(88,166,255,0.1); color:#58a6ff; border:1px solid rgba(88,166,255,0.25); border-radius:6px; padding:4px 10px; font-size:0.75rem;">&#128269; Tavily verified</span>
    <span style="background:rgba(255,106,61,0.1); color:#ff6a3d; border:1px solid rgba(255,106,61,0.25); border-radius:6px; padding:4px 10px; font-size:0.75rem;">&#128293; Firecrawl scraped</span>
    <span style="background:rgba(63,185,80,0.08); color:#3fb950; border:1px solid rgba(63,185,80,0.25); border-radius:6px; padding:4px 10px; font-size:0.75rem;">&#129302; Llama 3.3 written</span>
    </div>
    </div>
    {_unverified_banner}
    </div>
    """), unsafe_allow_html=True)

        # ── Push to Sheets ─────────────────────────────────────────────────────────
        _push_col, _info_col = st.columns([1, 3])
        with _push_col:
            if st.button("📊  Push to Google Sheets", type="primary", key="r3_push", use_container_width=True):
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
        with _info_col:
            st.markdown(_html("""
    <div style="background:rgba(22,25,33,0.5); border:1px solid #2d303a; border-radius:8px; padding:10px 14px; font-size:0.8rem; color:#8b949e; margin-top:4px;">
    &#128221; Sends all 10 sections to the <strong style="color:#c9d1d9;">Webpage Content</strong> tab in your Google Sheet. Each topic gets its own row. Open the sheet to copy content into your CMS.
    </div>
    """), unsafe_allow_html=True)

        st.markdown("<hr/>", unsafe_allow_html=True)

        # ── Content Preview Tabs ───────────────────────────────────────────────────
        st.markdown("<p style='color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1.8px; margin-bottom:8px;'>PREVIEW ALL 10 SECTIONS</p>", unsafe_allow_html=True)
        (
            tab_dl, tab_sources, tab_body, tab_wix, tab_seo,
            tab_faqs, tab_schema, tab_geo,
            tab_visual, tab_links, tab_raw
        ) = st.tabs([
            "📋 Decision Logic",
            "🔍 Proof & Sources",
            "📄 Page Body",
            "🌐 Wix HTML",
            "🔎 SEO Tags",
            "❓ FAQs",
            "🏷️ Schema Markup",
            "🌐 AI Citations",
            "📷 Image Briefs",
            "🔗 Internal Links",
            "🔧 Raw JSON",
        ])

        with tab_dl:
            st.markdown(_html("""
    <div style="background:rgba(88,166,255,0.06); border:1px solid rgba(88,166,255,0.2); border-radius:8px; padding:12px 16px; margin-bottom:14px; display:flex; gap:10px; align-items:flex-start;">
    <span style="font-size:1.2rem; flex-shrink:0;">&#128161;</span>
    <div style="font-size:0.83rem; color:#58a6ff; line-height:1.5;">
    <strong>What is this?</strong> A ready-to-send paragraph for Gary / Surendra explaining WHY we should build this page.
    It cites the exact Tavily search date, competitor names, and URLs &#8212; not just "we think this is a good idea."
    </div>
    </div>
    """), unsafe_allow_html=True)
            st.text_area(
                "Decision Logic",
                content.get("decision_logic", ""),
                height=220,
                key="r3_dl_text",
            )

        with tab_sources:
            st.markdown(_html("""
    <div style="background:rgba(88,166,255,0.06); border:1px solid rgba(88,166,255,0.2); border-radius:8px; padding:12px 16px; margin-bottom:16px; display:flex; gap:10px; align-items:flex-start;">
    <span style="font-size:1.2rem; flex-shrink:0;">&#128269;</span>
    <div style="font-size:0.83rem; color:#58a6ff; line-height:1.5;">
    <strong>What is this?</strong> The proof trail &#8212; exactly what Agent 1 searched, what Agent 2 scraped, and what Agent 3 actually used to write the content. If someone asks "how do you know this is a real gap?" &#8212; show them this tab.
    </div>
    </div>
    """), unsafe_allow_html=True)
            st.markdown("<h4 style='color:#e6edf3;'>Agent 1 — Tavily Gap Confirmation</h4>", unsafe_allow_html=True)
            st.markdown(_html(f"""
    <div class="glass-card" style="padding:16px;">
    <div style="margin-bottom:8px;"><span style="color:#8b949e; font-size:0.8rem;">Search:</span> <code>{_t(selected_topic.get('viact_search_query', ''))}</code> &#8594; <span style="color:#3fb950; font-weight:700;">0 dedicated solution pages</span></div>
    <div style="margin-bottom:8px;"><span style="color:#8b949e; font-size:0.8rem;">Confirmed:</span> <span style="color:#c9d1d9;">{_t(selected_topic.get('confirmed_at', ''))}</span></div>
    <div><span style="color:#8b949e; font-size:0.8rem;">Opportunity:</span> <span style="color:#ff6a3d; font-weight:700;">{_t(selected_topic.get('opportunity_score', '?'))}</span> &nbsp;&middot;&nbsp; <span style="color:#8b949e; font-size:0.8rem;">{_t(selected_topic.get('competitor_count', 0))} competitors covering this topic</span></div>
    </div>
    """), unsafe_allow_html=True)

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
                        st.markdown(f"<div style='color:#3fb950; font-size:0.84rem; margin-bottom:4px;'>&#10003; <code>{_t(url[:65])}</code> &mdash; {_t(result.get('word_count', 0))} words scraped</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='color:#f85149; font-size:0.84rem; margin-bottom:4px;'>&#x1F6AB; <code>{_t(url[:65])}</code> &mdash; ACCESS DENIED ({_t(result.get('error', 'unknown'))})</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='color:#484f58; font-size:0.84rem;'>No competitor URLs were scraped.</div>", unsafe_allow_html=True)

            used = content.get("data_sources_used", [])
            denied = content.get("access_denied_urls", [])
            if used:
                st.markdown(f"<div style='margin-top:12px; color:#8b949e; font-size:0.82rem;'>Agent 3 used: {_t(', '.join(used[:4]))}</div>", unsafe_allow_html=True)
            if denied:
                st.markdown(f"<div style='color:#f85149; font-size:0.82rem;'>Agent 3 skipped (ACCESS DENIED): {_t(', '.join(denied[:4]))}</div>", unsafe_allow_html=True)

        with tab_body:
            st.markdown(_html("""
    <div style="background:rgba(63,185,80,0.05); border:1px solid rgba(63,185,80,0.2); border-radius:8px; padding:12px 16px; margin-bottom:14px; display:flex; gap:10px; align-items:flex-start;">
    <span style="font-size:1.2rem; flex-shrink:0;">&#128196;</span>
    <div style="font-size:0.83rem; color:#3fb950; line-height:1.5;">
    <strong>What is this?</strong> The full webpage in Markdown format. Copy the text below and paste it into your CMS (WordPress, Webflow, Notion, etc.). Use "Preview" to see how it will look rendered.
    </div>
    </div>
    """), unsafe_allow_html=True)
            body = content.get("webpage_body", "")
            st.text_area("Webpage Body (Markdown — paste into CMS)", body, height=500, key="r3_body_text")
            with st.expander("👁️ Preview — see how the page renders"):
                st.markdown(body)

        with tab_wix:
            st.markdown(_html("""
    <div style="background:rgba(255,106,61,0.05); border:1px solid rgba(255,106,61,0.2); border-radius:8px; padding:12px 16px; margin-bottom:14px; display:flex; gap:10px; align-items:flex-start;">
    <span style="font-size:1.2rem; flex-shrink:0;">&#127760;</span>
    <div style="font-size:0.83rem; color:#ff6a3d; line-height:1.5;">
    <strong>Wix-Ready HTML.</strong> Copy the code below and paste it directly into Wix &rarr; <em>Add Elements &rarr; Embed &rarr; Custom Code</em> (or the Rich Text editor). No formatting will break. Tags used: &lt;h1&gt; &lt;h2&gt; &lt;p&gt; &lt;ul&gt; &lt;li&gt; &lt;strong&gt; &lt;a&gt; only.
    </div>
    </div>
    """), unsafe_allow_html=True)
            html_out = content.get("webpage_html", "")
            if not html_out:
                try:
                    from agent3_content_architect import build_webpage_html
                    html_out = build_webpage_html(content)
                except Exception:
                    html_out = "<p>HTML not available — regenerate content.</p>"
            st.text_area("Clean HTML (paste into Wix Embed Code)", html_out, height=500, key="r3_wix_html")
            st.caption("Tip: In Wix editor → Add Elements → Embed Code → Embed HTML → paste above")

        with tab_seo:
            st.markdown(_html("""
    <div style="background:rgba(88,166,255,0.06); border:1px solid rgba(88,166,255,0.2); border-radius:8px; padding:12px 16px; margin-bottom:14px; display:flex; gap:10px; align-items:flex-start;">
    <span style="font-size:1.2rem; flex-shrink:0;">&#128269;</span>
    <div style="font-size:0.83rem; color:#58a6ff; line-height:1.5;">
    <strong>What is this?</strong> Everything your web developer needs for SEO. Paste the meta title and description into your CMS &lt;head&gt;. Use the keywords for on-page copy. Heading map tells developers the H1/H2 structure.
    </div>
    </div>
    """), unsafe_allow_html=True)
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
                st.markdown(f"<div style='margin-bottom:8px;'><span style='color:#8b949e; font-size:0.82rem;'>Primary: </span><code>{_t(seo.get('primary_keyword', ''))}</code></div>", unsafe_allow_html=True)
                st.markdown("<div style='margin-bottom:8px; color:#8b949e; font-size:0.82rem;'>Secondary: " + " &nbsp;&middot;&nbsp; ".join(f"<code>{_t(k)}</code>" for k in seo.get("secondary_keywords", [])) + "</div>", unsafe_allow_html=True)
                st.markdown("<div style='margin-bottom:12px; color:#8b949e; font-size:0.82rem;'>LSI: " + " &nbsp;&middot;&nbsp; ".join(f"<code>{_t(k)}</code>" for k in seo.get("lsi_keywords", [])) + "</div>", unsafe_allow_html=True)
                st.markdown("<div style='color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;'>Heading Map</div>", unsafe_allow_html=True)
                for h in seo.get("heading_map", []):
                    depth = 1 if h.startswith("H1") else (2 if h.startswith("H2") else 3)
                    indent = (depth - 1) * 14
                    st.markdown(f"<div style='margin-left:{indent}px; color:#c9d1d9; font-size:0.84rem; margin-bottom:4px;'>{'&#9472;' * (depth-1)} {_t(h)}</div>", unsafe_allow_html=True)

        with tab_faqs:
            st.markdown(_html("""
    <div style="background:rgba(88,166,255,0.06); border:1px solid rgba(88,166,255,0.2); border-radius:8px; padding:12px 16px; margin-bottom:14px; display:flex; gap:10px; align-items:flex-start;">
    <span style="font-size:1.2rem; flex-shrink:0;">&#10067;</span>
    <div style="font-size:0.83rem; color:#58a6ff; line-height:1.5;">
    <strong>What is this?</strong> Two types: <strong>Schema FAQs</strong> (5 short answers &#8212; become the JSON-LD markup that Google shows as rich results in search) and <strong>Extended FAQs</strong> (2 longer answers for the actual webpage). Copy both to your CMS.
    </div>
    </div>
    """), unsafe_allow_html=True)
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
            st.markdown(_html("""
    <div style="background:rgba(88,166,255,0.06); border:1px solid rgba(88,166,255,0.2); border-radius:8px; padding:12px 16px; margin-bottom:14px; display:flex; gap:10px; align-items:flex-start;">
    <span style="font-size:1.2rem; flex-shrink:0;">&#127991;</span>
    <div style="font-size:0.83rem; color:#58a6ff; line-height:1.5;">
    <strong>What is this?</strong> Structured data code for Google. Give this to your developer and tell them: "Add this inside a &lt;script type=&rdquo;application/ld+json&rdquo;&gt; tag in the page &lt;head&gt;." It makes Google show your FAQs directly in search results.
    </div>
    </div>
    """), unsafe_allow_html=True)
            st.code(content.get("schema_json_ld", ""), language="json")

        with tab_geo:
            geo = content.get("geo_package", {})
            st.markdown(_html("""
    <div style="background:rgba(88,166,255,0.06); border:1px solid rgba(88,166,255,0.2); border-radius:8px; padding:12px 16px; margin-bottom:14px; display:flex; gap:10px; align-items:flex-start;">
    <span style="font-size:1.2rem; flex-shrink:0;">&#127760;</span>
    <div style="font-size:0.83rem; color:#58a6ff; line-height:1.5;">
    <strong>What is this?</strong> The opening 200 words are written specifically so that AI tools like ChatGPT, Perplexity, and Google AI Overviews will quote viAct when someone searches this topic. Use this exact text as the first paragraph of your webpage.
    </div>
    </div>
    """), unsafe_allow_html=True)
            st.markdown("<div style='color:#e6edf3; font-weight:600; margin-bottom:8px;'>Opening 200 Words — AI-citation optimized:</div>", unsafe_allow_html=True)
            st.text_area("Opening 200 words", geo.get("opening_200_words", ""), height=180, key="r3_geo")
            st.markdown("<div style='color:#e6edf3; font-weight:600; margin:14px 0 8px;'>Citation Framing Tips:</div>", unsafe_allow_html=True)
            for tip in geo.get("citation_framing_tips", []):
                st.markdown(f"<div style='background:rgba(22,25,33,0.6); border:1px solid #2d303a; border-radius:6px; padding:8px 12px; margin-bottom:6px; color:#c9d1d9; font-size:0.85rem;'>&#8594; {_t(tip)}</div>", unsafe_allow_html=True)

        with tab_visual:
            prompts = content.get("nano_banana_prompts", content.get("visual_strategy", []))
            st.markdown("<div style='color:#8b949e; font-size:0.82rem; margin-bottom:12px;'>Realistic photography, APAC context, human-centered — not CGI. For use with Nano Banana 2.</div>", unsafe_allow_html=True)
            for i, v in enumerate(prompts, 1):
                with st.expander(f"Image {i} — {v.get('placement', '')}"):
                    st.text_area(f"Prompt {i}", v.get("prompt", ""), height=140, key=f"r3_vis_{i}")
                    st.markdown(f"<div style='color:#8b949e; font-size:0.82rem; margin-top:6px;'><strong style='color:#e6edf3;'>Alt text:</strong> {_t(v.get('alt_text', ''))}</div>", unsafe_allow_html=True)

        with tab_links:
            st.markdown("<div style='color:#e6edf3; font-weight:600; margin-bottom:10px;'>Internal Links — verified viAct.ai URLs only:</div>", unsafe_allow_html=True)
            for link in content.get("internal_links", []):
                url_val = link.get("url", "")
                st.markdown(
                    f"<div style='background:rgba(22,25,33,0.6); border:1px solid #2d303a; border-radius:6px; padding:10px 14px; margin-bottom:8px;'>"
                    f"<div style='color:#ff6a3d; font-weight:600; font-size:0.88rem;'>{_t(link.get('anchor_text', ''))}</div>"
                    f"<div style='margin:4px 0;'><a href='{_t(url_val)}' target='_blank' style='color:#58a6ff; font-size:0.82rem;'>{_t(url_val)}</a></div>"
                    f"<div style='color:#8b949e; font-size:0.8rem;'>{_t(link.get('context', ''))}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        with tab_raw:
            st.json(content)


with tab_industry:
    # ── Session state ─────────────────────────────────────────────────────────
    if "ip_step" not in st.session_state:
        st.session_state["ip_step"] = 0

    ip_step = st.session_state["ip_step"]

    if ip_step > 0:
        st.write("")
        if st.button("↩ Start Over", key="ip_reset"):
            for _k in [_k for _k in st.session_state if _k.startswith("ip_")]:
                del st.session_state[_k]
            st.rerun()

    st.write("")

    # =========================================================================
    # INDUSTRY STEP 0 — Select Industry & Generate
    # =========================================================================
    if ip_step == 0:
        st.markdown(
            "<p style='color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1.8px; margin-bottom:12px;'>GENERATE A FULL INDUSTRY VERTICAL LANDING PAGE</p>",
            unsafe_allow_html=True,
        )
        st.markdown(_html(
            '<div class="glass-card" style="margin-bottom:18px;">'
            '<div style="color:#8b949e; font-size:0.82rem; line-height:1.7;">'
            "Select your industry. The system will:<br>"
            "&nbsp;1. Scrape viAct existing industry page (tone reference via Firecrawl)<br>"
            "&nbsp;2. Scrape 2-3 competitor industry pages (Firecrawl)<br>"
            "&nbsp;3. Generate a complete 8-section landing page: SEO, FAQs, 11 image prompts, Wix HTML (Llama 3.3 70B)"
            "</div></div>"
        ), unsafe_allow_html=True)

        from agent3_content_architect import INDUSTRY_VIACT_URLS, INDUSTRY_COMPETITOR_URLS

        _ind_col, _ref_col = st.columns([1, 1], gap="medium")
        with _ind_col:
            ip_industry = st.selectbox(
                "Industry",
                list(INDUSTRY_VIACT_URLS.keys()),
                key="ip_industry_select",
            )
        with _ref_col:
            ip_yt = st.text_input(
                "YouTube Video URL (optional — embedded in hero)",
                placeholder="https://www.youtube.com/watch?v=...",
                key="ip_yt_url",
            )

        ip_refs = st.text_area(
            "Reference Material (optional — paste viAct project stats, case study numbers, MOM data)",
            height=110,
            key="ip_refs_text",
        )

        st.write("")

        if st.button("🏭  Generate Industry Page", type="primary", key="ip_generate"):
            _industry_slug = INDUSTRY_VIACT_URLS[ip_industry].rsplit("/", 1)[-1]
            _viact_url     = INDUSTRY_VIACT_URLS[ip_industry]
            _comp_urls     = INDUSTRY_COMPETITOR_URLS.get(ip_industry, [])
            _refs_combined = ip_refs.strip()
            if ip_yt.strip():
                _refs_combined = f"Hero YouTube Video URL: {ip_yt.strip()}\n\n" + _refs_combined

            import sys as _sys
            _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
            from agent2_data_extractor import extract_competitor_content
            from agent3_content_architect import generate_industry_page

            _prog = st.empty()

            with _prog.container():
                st.info("Step 1/3 — Scraping viAct industry page (tone reference)...")
            try:
                _viact_scraped = extract_competitor_content([_viact_url])
                _viact_md = _viact_scraped.get(_viact_url, {}).get("markdown", "")
            except Exception as _e:
                _viact_md = ""

            with _prog.container():
                st.info(f"Step 2/3 — Scraping {len(_comp_urls)} competitor industry pages (Firecrawl)...")
            try:
                _comp_data = extract_competitor_content(_comp_urls)
            except Exception:
                _comp_data = {}

            with _prog.container():
                st.info("Step 3/3 — Generating 8-section industry page (Llama 3.3 70B)...")
            try:
                _result = generate_industry_page(
                    industry_name=ip_industry,
                    industry_slug=_industry_slug,
                    viact_page_content=_viact_md,
                    competitor_content=_comp_data,
                    references=_refs_combined,
                    viact_pages=[],
                )
                st.session_state["ip_content"]         = _result
                st.session_state["ip_competitor_data"] = _comp_data
                st.session_state["ip_industry_label"]  = ip_industry
                st.session_state["ip_viact_url"]       = _viact_url
                st.session_state["ip_step"]            = 1
                _prog.empty()
                st.rerun()
            except Exception as _e:
                _prog.empty()
                st.error(f"Generation failed: {_e}")

    # =========================================================================
    # INDUSTRY STEP 1 — Preview + Push to Sheets
    # =========================================================================
    elif ip_step == 1:
        _ip_content    = st.session_state["ip_content"]
        _ip_comp_data  = st.session_state.get("ip_competitor_data", {})
        _ip_label      = st.session_state.get("ip_industry_label", "")
        _ip_viact_url  = st.session_state.get("ip_viact_url", "")

        st.markdown(_html(
            '<div class="glass-card" style="border-color:rgba(63,185,80,0.3); background:rgba(22,25,33,0.8);">'
            '<div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;">'
            '<div style="display:flex; align-items:center; gap:12px;">'
            '<div style="background:rgba(63,185,80,0.15); border:1px solid #238636; border-radius:50%; width:40px; height:40px; display:flex; align-items:center; justify-content:center; font-size:1.2rem; flex-shrink:0;">&#127970;</div>'
            '<div>'
            '<div style="color:#3fb950; font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:1.5px; margin-bottom:3px;">Industry Landing Page Ready</div>'
            f'<h3 style="margin:0; color:#e6edf3; font-size:1.1rem;">{_t(_ip_label)}</h3>'
            '</div></div>'
            '<div style="display:flex; gap:8px; flex-wrap:wrap;">'
            '<span style="background:rgba(255,106,61,0.1); color:#ff6a3d; border:1px solid rgba(255,106,61,0.25); border-radius:6px; padding:4px 10px; font-size:0.75rem;">&#128293; Firecrawl scraped</span>'
            '<span style="background:rgba(63,185,80,0.08); color:#3fb950; border:1px solid rgba(63,185,80,0.25); border-radius:6px; padding:4px 10px; font-size:0.75rem;">&#129302; Llama 3.3 written</span>'
            '<span style="background:rgba(88,166,255,0.1); color:#58a6ff; border:1px solid rgba(88,166,255,0.25); border-radius:6px; padding:4px 10px; font-size:0.75rem;">&#127970; 8-section structure</span>'
            '</div></div></div>'
        ), unsafe_allow_html=True)

        _ip_push_col, _ip_info_col = st.columns([1, 3])
        with _ip_push_col:
            if st.button("📊  Push to Google Sheets", type="primary", key="ip_push", use_container_width=True):
                try:
                    from push_to_sheets import push_webpage
                    push_webpage(
                        content=_ip_content,
                        decision_logic=_ip_content.get("decision_logic", ""),
                        input_source=f"Industry Page — {_ip_label}",
                        competitor_urls=list(_ip_comp_data.keys()),
                        unverified=False,
                    )
                    _sheet_url = f"https://docs.google.com/spreadsheets/d/{os.getenv('SHEET_ID', '')}/edit#gid=1093335602"
                    st.success(f"✅ Industry page pushed — [Open Sheet ↗]({_sheet_url})")
                except Exception as _e:
                    st.error(f"Sheets error: {_e}")
        with _ip_info_col:
            st.markdown(_html(
                '<div style="background:rgba(22,25,33,0.5); border:1px solid #2d303a; border-radius:8px; padding:10px 14px; font-size:0.8rem; color:#8b949e; margin-top:4px;">'
                '&#128221; Writes to the <strong style="color:#c9d1d9;">Webpage Content</strong> tab. Input Source = "Industry Page — [name]".'
                '</div>'
            ), unsafe_allow_html=True)

        st.markdown("<hr/>", unsafe_allow_html=True)
        st.markdown("<p style='color:#8b949e; font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:1.8px; margin-bottom:8px;'>PREVIEW ALL SECTIONS</p>", unsafe_allow_html=True)

        (
            _ip_tab_dl, _ip_tab_sources, _ip_tab_body, _ip_tab_wix, _ip_tab_cms,
            _ip_tab_seo, _ip_tab_faqs, _ip_tab_schema, _ip_tab_geo,
            _ip_tab_visual, _ip_tab_links, _ip_tab_raw,
        ) = st.tabs([
            "📋 Decision Logic",
            "🔍 Proof & Sources",
            "📄 Page Body",
            "🌐 Wix HTML",
            "🗂️ Wix CMS Fields",
            "🔎 SEO Tags",
            "❓ FAQs",
            "🏷️ Schema Markup",
            "🌐 AI Citations",
            "📷 Image Briefs",
            "🔗 Internal Links",
            "🔧 Raw JSON",
        ])

        with _ip_tab_dl:
            st.text_area("Decision Logic", _ip_content.get("decision_logic", ""), height=220, key="ip_dl_text")

        with _ip_tab_sources:
            st.markdown("<h4 style='color:#e6edf3;'>viAct Industry Page (Tone Reference)</h4>", unsafe_allow_html=True)
            _viact_res = _ip_comp_data.get(_ip_viact_url, {})
            if _viact_res.get("success"):
                st.markdown(f"<div style='color:#3fb950; font-size:0.84rem; margin-bottom:4px;'>&#10003; <code>{_t(_ip_viact_url[:70])}</code> &mdash; {_viact_res.get('word_count', 0)} words scraped</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='color:#f85149; font-size:0.84rem; margin-bottom:4px;'>&#x1F6AB; <code>{_t(_ip_viact_url[:70])}</code> &mdash; ACCESS DENIED (fresh content generated)</div>", unsafe_allow_html=True)
            st.markdown("<hr/><h4 style='color:#e6edf3;'>Competitor Industry Pages (Firecrawl)</h4>", unsafe_allow_html=True)
            for _url, _res in _ip_comp_data.items():
                if _url == _ip_viact_url:
                    continue
                if _res.get("success"):
                    st.markdown(f"<div style='color:#3fb950; font-size:0.84rem; margin-bottom:4px;'>&#10003; <code>{_t(_url[:65])}</code> &mdash; {_res.get('word_count', 0)} words</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='color:#f85149; font-size:0.84rem; margin-bottom:4px;'>&#x1F6AB; <code>{_t(_url[:65])}</code> &mdash; ACCESS DENIED</div>", unsafe_allow_html=True)

        with _ip_tab_body:
            _ip_body = _ip_content.get("webpage_body", "")
            st.text_area("Webpage Body (Markdown — copy-paste into Wix CMS)", _ip_body, height=500, key="ip_body_text")
            with st.expander("👁️ Preview — see how the page renders"):
                st.markdown(_ip_body)

        with _ip_tab_wix:
            _ip_html_out = _ip_content.get("webpage_html", "")
            if not _ip_html_out:
                try:
                    from agent3_content_architect import build_webpage_html
                    _ip_html_out = build_webpage_html(_ip_content)
                except Exception:
                    _ip_html_out = "<p>HTML not available — regenerate content.</p>"
            st.text_area("Clean HTML (paste into Wix Embed Code)", _ip_html_out, height=500, key="ip_wix_html")
            st.caption("Tip: In Wix editor → Add Elements → Embed Code → Embed HTML → paste above")

        with _ip_tab_cms:
            _ip_cms = _ip_content.get("industry_cms_fields", {})
            if not _ip_cms:
                st.info("No CMS fields in this output — regenerate to get individual Wix CMS copy-paste fields.")
            else:
                st.markdown(
                    "<div style='background:rgba(88,166,255,0.06); border:1px solid rgba(88,166,255,0.2); border-radius:8px; padding:12px 16px; margin-bottom:14px; font-size:0.83rem; color:#58a6ff;'>"
                    "<strong>Wix CMS Fields</strong> — Each field maps to one dynamic field in your Wix CMS dataset. Copy one field at a time directly into the matching CMS field."
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.markdown("<div style='color:#ff6a3d; font-weight:700; font-size:0.9rem; margin:10px 0 6px; text-transform:uppercase; letter-spacing:1.2px;'>Hero Section</div>", unsafe_allow_html=True)
                st.text_input("Hero Subheadline", _ip_cms.get("hero_subheadline", ""), key="ip_cms_hero_sub")
                st.text_area("Hero Body Copy", _ip_cms.get("hero_body_copy", ""), height=90, key="ip_cms_hero_body")

                st.markdown("<div style='color:#ff6a3d; font-weight:700; font-size:0.9rem; margin:14px 0 6px; text-transform:uppercase; letter-spacing:1.2px;'>Impact Section</div>", unsafe_allow_html=True)
                st.text_input("Impact Section Title", _ip_cms.get("impact_section_title", ""), key="ip_cms_impact_title")
                st.text_input("Impact Subtitle", _ip_cms.get("impact_subtitle", ""), key="ip_cms_impact_sub")

                st.markdown("<div style='color:#ff6a3d; font-weight:700; font-size:0.9rem; margin:14px 0 6px; text-transform:uppercase; letter-spacing:1.2px;'>Metrics (3 Stats)</div>", unsafe_allow_html=True)
                for _mi, _met in enumerate(_ip_cms.get("metrics", []), 1):
                    _mc1, _mc2 = st.columns([1, 2])
                    with _mc1:
                        st.text_input(f"Metric {_mi} Label", _met.get("label", ""), key=f"ip_cms_met_label_{_mi}")
                    with _mc2:
                        st.text_input(f"Metric {_mi} Description", _met.get("description", ""), key=f"ip_cms_met_desc_{_mi}")

                st.markdown("<div style='color:#ff6a3d; font-weight:700; font-size:0.9rem; margin:14px 0 6px; text-transform:uppercase; letter-spacing:1.2px;'>Use Cases Section</div>", unsafe_allow_html=True)
                st.text_input("Use Cases Section Title", _ip_cms.get("use_cases_section_title", ""), key="ip_cms_uc_section_title")
                for _uci, _uc in enumerate(_ip_cms.get("use_cases", []), 1):
                    with st.expander(f"Use Case {_uci}: {_uc.get('title', '')}"):
                        st.text_input(f"UC{_uci} Title", _uc.get("title", ""), key=f"ip_cms_uc_title_{_uci}")
                        st.text_area(f"UC{_uci} Description", _uc.get("description", ""), height=80, key=f"ip_cms_uc_desc_{_uci}")

                st.markdown("<div style='color:#ff6a3d; font-weight:700; font-size:0.9rem; margin:14px 0 6px; text-transform:uppercase; letter-spacing:1.2px;'>Solutions & viGent</div>", unsafe_allow_html=True)
                st.text_area("Solutions Description", _ip_cms.get("solutions_description", ""), height=80, key="ip_cms_solutions")
                st.text_area("viGent Description", _ip_cms.get("vigent_description", ""), height=100, key="ip_cms_vigent")

                st.markdown("<div style='color:#ff6a3d; font-weight:700; font-size:0.9rem; margin:14px 0 6px; text-transform:uppercase; letter-spacing:1.2px;'>Testimonials (5)</div>", unsafe_allow_html=True)
                for _ti, _test in enumerate(_ip_cms.get("testimonials", []), 1):
                    with st.expander(f"Testimonial {_ti} — {_test.get('source', '')}"):
                        st.text_area(f"T{_ti} Quote", _test.get("quote", ""), height=90, key=f"ip_cms_test_quote_{_ti}")
                        st.text_input(f"T{_ti} Source", _test.get("source", ""), key=f"ip_cms_test_src_{_ti}")

                st.markdown("<div style='color:#ff6a3d; font-weight:700; font-size:0.9rem; margin:14px 0 6px; text-transform:uppercase; letter-spacing:1.2px;'>CTA Section</div>", unsafe_allow_html=True)
                st.text_input("CTA Headline", _ip_cms.get("cta_headline", ""), key="ip_cms_cta_headline")
                st.text_area("CTA Description", _ip_cms.get("cta_description", ""), height=80, key="ip_cms_cta_desc")

        with _ip_tab_seo:
            _ip_seo = _ip_content.get("seo_suite", {})
            _c1, _c2 = st.columns(2)
            with _c1:
                st.text_input("Meta Title", _ip_seo.get("meta_title", ""), key="ip_meta_title")
                st.caption(f"{len(_ip_seo.get('meta_title', ''))} chars — target 50-60")
                st.text_area("Meta Description", _ip_seo.get("meta_description", ""), height=90, key="ip_meta_desc")
                st.caption(f"{len(_ip_seo.get('meta_description', ''))} chars — target 140-155")
                st.text_input("Canonical Slug", _ip_seo.get("canonical_url_slug", ""), key="ip_slug")
            with _c2:
                st.markdown(f"<div style='margin-bottom:8px;'><span style='color:#8b949e; font-size:0.82rem;'>Primary: </span><code>{_t(_ip_seo.get('primary_keyword', ''))}</code></div>", unsafe_allow_html=True)
                st.markdown("<div style='margin-bottom:8px; color:#8b949e; font-size:0.82rem;'>Secondary: " + " &nbsp;&middot;&nbsp; ".join(f"<code>{_t(k)}</code>" for k in _ip_seo.get("secondary_keywords", [])) + "</div>", unsafe_allow_html=True)
                st.markdown("<div style='margin-bottom:12px; color:#8b949e; font-size:0.82rem;'>LSI: " + " &nbsp;&middot;&nbsp; ".join(f"<code>{_t(k)}</code>" for k in _ip_seo.get("lsi_keywords", [])) + "</div>", unsafe_allow_html=True)
                for _h in _ip_seo.get("heading_map", []):
                    _depth = 1 if _h.startswith("H1") else (2 if _h.startswith("H2") else 3)
                    st.markdown(f"<div style='margin-left:{(_depth-1)*14}px; color:#c9d1d9; font-size:0.84rem; margin-bottom:4px;'>{_t(_h)}</div>", unsafe_allow_html=True)

        with _ip_tab_faqs:
            st.markdown("<div style='color:#e6edf3; font-weight:700; margin-bottom:12px;'>Schema FAQs <span style='color:#8b949e; font-size:0.82rem; font-weight:400;'>— 5 items · used in JSON-LD rich results</span></div>", unsafe_allow_html=True)
            for _i, _faq in enumerate(_ip_content.get("schema_faqs", []), 1):
                with st.expander(f"Q{_i}: {_faq.get('question', '')}"):
                    st.write(_faq.get("answer", ""))
                    st.caption(f"{len(_faq.get('answer', '').split())} words")
            st.markdown("<hr/><div style='color:#e6edf3; font-weight:700; margin:12px 0;'>Extended FAQs <span style='color:#8b949e; font-size:0.82rem; font-weight:400;'>— 2 items · 80-120 words · on-page only</span></div>", unsafe_allow_html=True)
            for _i, _faq in enumerate(_ip_content.get("extended_faqs", []), 1):
                with st.expander(f"Extended Q{_i}: {_faq.get('question', '')}"):
                    st.write(_faq.get("answer", ""))

        with _ip_tab_schema:
            st.markdown(
                "<div style='background:rgba(88,166,255,0.06); border:1px solid rgba(88,166,255,0.2); border-radius:8px; padding:12px 16px; margin-bottom:14px; font-size:0.83rem; color:#58a6ff;'>"
                "<strong>What is this?</strong> Add this inside a &lt;script type=\"application/ld+json\"&gt; tag in the page &lt;head&gt;. Makes Google show FAQs as rich results."
                "</div>",
                unsafe_allow_html=True,
            )
            st.code(_ip_content.get("schema_json_ld", ""), language="json")

        with _ip_tab_geo:
            _ip_geo = _ip_content.get("geo_package", {})
            st.markdown("<div style='color:#e6edf3; font-weight:600; margin-bottom:8px;'>Opening 200 Words — AI-citation optimized:</div>", unsafe_allow_html=True)
            st.text_area("Opening 200 words", _ip_geo.get("opening_200_words", ""), height=180, key="ip_geo")
            st.markdown("<div style='color:#e6edf3; font-weight:600; margin:14px 0 8px;'>Citation Framing Tips:</div>", unsafe_allow_html=True)
            for _tip in _ip_geo.get("citation_framing_tips", []):
                st.markdown(f"<div style='background:rgba(22,25,33,0.6); border:1px solid #2d303a; border-radius:6px; padding:8px 12px; margin-bottom:6px; color:#c9d1d9; font-size:0.85rem;'>&#8594; {_t(_tip)}</div>", unsafe_allow_html=True)

        with _ip_tab_visual:
            _ip_prompts = _ip_content.get("nano_banana_prompts", [])
            st.markdown("<div style='color:#8b949e; font-size:0.82rem; margin-bottom:12px;'>11 image prompts with exact pixel dimensions (6 use cases + viGent dashboard + 4 reviewer headshots). Use with Nano Banana 2.</div>", unsafe_allow_html=True)
            for _i, _v in enumerate(_ip_prompts, 1):
                with st.expander(f"Image {_i} — {_v.get('placement', '')}"):
                    st.text_area(f"Prompt {_i}", _v.get("prompt", ""), height=140, key=f"ip_vis_{_i}")
                    st.markdown(f"<div style='color:#8b949e; font-size:0.82rem; margin-top:6px;'><strong style='color:#e6edf3;'>Alt text:</strong> {_t(_v.get('alt_text', ''))}</div>", unsafe_allow_html=True)

        with _ip_tab_links:
            st.markdown("<div style='color:#e6edf3; font-weight:600; margin-bottom:10px;'>Internal Links — verified viAct.ai URLs only:</div>", unsafe_allow_html=True)
            for _link in _ip_content.get("internal_links", []):
                _url_val = _link.get("url", "")
                st.markdown(
                    f"<div style='background:rgba(22,25,33,0.6); border:1px solid #2d303a; border-radius:6px; padding:10px 14px; margin-bottom:8px;'>"
                    f"<div style='color:#ff6a3d; font-weight:600; font-size:0.88rem;'>{_t(_link.get('anchor_text', ''))}</div>"
                    f"<div style='margin:4px 0;'><a href='{_t(_url_val)}' target='_blank' style='color:#58a6ff; font-size:0.82rem;'>{_t(_url_val)}</a></div>"
                    f"<div style='color:#8b949e; font-size:0.8rem;'>{_t(_link.get('context', ''))}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        with _ip_tab_raw:
            st.json(_ip_content)
