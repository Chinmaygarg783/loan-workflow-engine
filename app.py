"""
app.py — Streamlit frontend for the Loan Workflow Decision Engine.

Run alongside the FastAPI server:
  Terminal 1: uvicorn main:app --reload --port 8000
  Terminal 2: streamlit run app.py
"""

import streamlit as st
import requests
import json
import uuid
from datetime import datetime

API_BASE = "http://localhost:8000"

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LoanFlow — Decision Engine",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

  html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

  /* Sidebar */
  section[data-testid="stSidebar"] {
    background: #0b1120;
    border-right: 1px solid #1e2d45;
  }
  section[data-testid="stSidebar"] * { color: #cbd5e1 !important; }
  section[data-testid="stSidebar"] .stRadio label { font-size: 0.95rem; padding: 4px 0; }

  /* Main background */
  .stApp { background: #f0f4f8; }

  /* Top header strip */
  .top-bar {
    background: linear-gradient(135deg, #0b1120 0%, #0f2044 100%);
    border-radius: 14px;
    padding: 24px 32px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .top-bar h1 { color: #fff; font-size: 1.7rem; font-weight: 700; margin: 0; }
  .top-bar span { color: #64b5f6; font-size: 0.85rem; font-family: 'DM Mono', monospace; }

  /* Cards */
  .card {
    background: #ffffff;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
    margin-bottom: 16px;
    border: 1px solid #e2e8f0;
  }
  .card h3 { font-size: 1rem; font-weight: 600; color: #1e293b; margin: 0 0 16px; }

  /* Decision badge */
  .badge {
    display: inline-block;
    padding: 6px 18px;
    border-radius: 999px;
    font-weight: 700;
    font-size: 0.9rem;
    letter-spacing: 0.05em;
  }
  .badge-approved  { background: #d1fae5; color: #065f46; }
  .badge-rejected  { background: #fee2e2; color: #991b1b; }
  .badge-review    { background: #fef3c7; color: #92400e; }
  .badge-pending   { background: #e0e7ff; color: #3730a3; }
  .badge-failed    { background: #f1f5f9; color: #475569; }

  /* Stage pill */
  .stage-pill {
    display: inline-block;
    background: #eff6ff;
    color: #1d4ed8;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 0.78rem;
    font-family: 'DM Mono', monospace;
    font-weight: 500;
  }

  /* Audit row */
  .audit-row {
    display: flex;
    gap: 16px;
    align-items: flex-start;
    padding: 10px 0;
    border-bottom: 1px solid #f1f5f9;
  }
  .audit-row:last-child { border-bottom: none; }
  .audit-time  { font-size: 0.72rem; font-family: 'DM Mono', monospace; color: #94a3b8; white-space: nowrap; min-width: 160px; }
  .audit-stage { font-size: 0.72rem; font-family: 'DM Mono', monospace; background: #f1f5f9; color: #475569; border-radius: 4px; padding: 2px 6px; white-space: nowrap; }
  .audit-event { font-size: 0.85rem; color: #334155; }

  /* AI card */
  .ai-card {
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
    border: 1px solid #bae6fd;
    border-radius: 12px;
    padding: 20px;
    margin-top: 12px;
  }
  .ai-card h4 { color: #0369a1; font-size: 0.95rem; margin: 0 0 10px; }
  .ai-label   { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; font-weight: 600; }
  .ai-value   { font-size: 0.92rem; color: #1e293b; margin-bottom: 10px; }

  /* Confidence bar */
  .conf-track { background: #e2e8f0; border-radius: 99px; height: 8px; margin: 4px 0 12px; }
  .conf-fill  { height: 8px; border-radius: 99px; background: linear-gradient(90deg, #3b82f6, #06b6d4); }

  /* Metric row */
  .metric-row { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .metric-box {
    flex: 1; min-width: 100px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px 16px;
  }
  .metric-label { font-size: 0.72rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.07em; font-weight: 600; }
  .metric-value { font-size: 1.4rem; font-weight: 700; color: #0f172a; margin-top: 4px; }

  /* Rule chip */
  .rule-chip {
    display: inline-block;
    background: #fef2f2;
    color: #b91c1c;
    border: 1px solid #fecaca;
    border-radius: 6px;
    font-size: 0.78rem;
    padding: 3px 8px;
    margin: 2px;
    font-family: 'DM Mono', monospace;
  }
  .rule-chip-pass {
    background: #f0fdf4;
    color: #15803d;
    border: 1px solid #bbf7d0;
  }

  /* Section divider */
  .section-title {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #94a3b8;
    margin: 20px 0 8px;
  }

  /* Hide streamlit branding */
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def api(method: str, path: str, **kwargs):
    try:
        r = requests.request(method, f"{API_BASE}{path}", timeout=30, **kwargs)
        return r.json(), r.status_code
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot connect to API server. Is it running? `uvicorn main:app --reload`"}, 503
    except Exception as e:
        return {"error": str(e)}, 500


def decision_badge(decision: str) -> str:
    if not decision:
        return ""
    cls = {
        "APPROVED":      "badge-approved",
        "REJECTED":      "badge-rejected",
        "MANUAL_REVIEW": "badge-review",
        "FAILED":        "badge-failed",
    }.get(decision, "badge-pending")
    return f'<span class="badge {cls}">{decision}</span>'


def fmt_ts(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts


# ── Sidebar nav ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏦 LoanFlow")
    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["📋 Submit Application", "🔍 Check Status", "📜 Audit Trail", "⚙️ Config & Rules", "🛡️ Manual Override"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    health, code = api("GET", "/health")
    if code == 200:
        st.success("✅ API server online")
    else:
        st.error("❌ API server offline")


# ── Page: Submit Application ───────────────────────────────────────────────────
if page == "📋 Submit Application":
    st.markdown("""
    <div class="top-bar">
      <h1>📋 Submit Loan Application</h1>
      <span>Configurable Workflow Decision Engine</span>
    </div>
    """, unsafe_allow_html=True)

    col_form, col_info = st.columns([3, 2], gap="large")

    with col_form:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Applicant Details</div>', unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Full Name", value="Alice Smith", placeholder="John Doe")
            age  = st.number_input("Age", min_value=18, max_value=100, value=34)
        with c2:
            request_id = st.text_input("Request ID", value=f"LOAN-{uuid.uuid4().hex[:6].upper()}")
            idem_key   = st.text_input("Idempotency Key (optional)", value="", placeholder="Leave blank to auto-generate")

        st.markdown('<div class="section-title">Financial Details</div>', unsafe_allow_html=True)
        c3, c4 = st.columns(2)
        with c3:
            income      = st.number_input("Annual Income ($)", min_value=1000, max_value=10_000_000, value=85_000, step=1000)
            credit_score = st.slider("Credit Score", min_value=300, max_value=850, value=720)
        with c4:
            loan_amount = st.number_input("Loan Amount ($)", min_value=1000, max_value=10_000_000, value=200_000, step=1000)
            docs        = st.checkbox("Documents Submitted", value=True)

        # Live ratio preview
        ratio = loan_amount / income if income > 0 else 0
        ratio_color = "#15803d" if ratio <= 3 else "#d97706" if ratio <= 5 else "#dc2626"
        st.markdown(f"""
        <div style="background:#f8fafc;border-radius:8px;padding:12px 16px;border:1px solid #e2e8f0;margin-top:8px">
          <span style="font-size:0.78rem;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.07em">
            Loan-to-Income Ratio
          </span>
          <span style="font-size:1.4rem;font-weight:700;color:{ratio_color};margin-left:12px">{ratio:.2f}x</span>
          <span style="font-size:0.8rem;color:#94a3b8;margin-left:8px">{'✅ Good' if ratio<=3 else '⚠️ Borderline' if ratio<=5 else '🚫 Over limit'}</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        submit = st.button("🚀 Submit Application", type="primary", use_container_width=True)

    with col_info:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Decision Rules Preview</div>', unsafe_allow_html=True)

        cfg, _ = api("GET", "/config/rules")
        if "rules" in cfg:
            for rule in sorted(cfg["rules"], key=lambda r: r.get("priority", 99)):
                icon = "🚫" if rule.get("action") == "REJECT" else "✅"
                st.markdown(f"""
                <div style="padding:8px 0;border-bottom:1px solid #f1f5f9">
                  <div style="font-size:0.8rem;font-weight:600;color:#334155">{icon} {rule['name'].replace('_',' ').title()}</div>
                  <div style="font-size:0.75rem;color:#64748b;margin-top:2px">{rule['description']}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Ambiguous Thresholds (→ AI Review)</div>', unsafe_allow_html=True)
        if "workflow" in cfg:
            t = cfg["workflow"]["ambiguous_thresholds"]
            st.markdown(f"""
            <div style="font-size:0.82rem;color:#334155;line-height:2">
              🤖 Credit Score: <b>{t['credit_score_min']} – {t['credit_score_max']}</b><br>
              🤖 Income: <b>${t['income_min']:,} – ${t['income_max']:,}</b><br>
              🤖 Missing Documents: <b>always escalated</b>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Handle submission ──────────────────────────────────────────────────────
    if submit:
        payload = {
            "request_id":          request_id,
            "name":                name,
            "age":                 age,
            "income":              income,
            "loan_amount":         loan_amount,
            "credit_score":        credit_score,
            "documents_submitted": docs,
        }
        headers = {}
        if idem_key.strip():
            headers["idempotency-key"] = idem_key.strip()

        with st.spinner("Processing application through workflow engine..."):
            result, status = api("POST", "/applications", json=payload, headers=headers)

        if "error" in result:
            st.error(result["error"])
        else:
            decision = result.get("final_decision", "")
            stage    = result.get("current_stage", "")

            # Decision header
            st.markdown(f"""
            <div style="background:{'#d1fae5' if decision=='APPROVED' else '#fee2e2' if decision=='REJECTED' else '#fef3c7'};
                        border-radius:12px;padding:20px 28px;margin:16px 0;
                        border:1px solid {'#6ee7b7' if decision=='APPROVED' else '#fca5a5' if decision=='REJECTED' else '#fde68a'}">
              <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;
                          color:{'#065f46' if decision=='APPROVED' else '#991b1b' if decision=='REJECTED' else '#92400e'}">
                Final Decision
              </div>
              <div style="font-size:2rem;font-weight:700;margin:4px 0;
                          color:{'#059669' if decision=='APPROVED' else '#dc2626' if decision=='REJECTED' else '#d97706'}">
                {'✅ APPROVED' if decision=='APPROVED' else '🚫 REJECTED' if decision=='REJECTED' else '👁️ '+decision}
              </div>
              <div style="font-size:0.88rem;color:{'#065f46' if decision=='APPROVED' else '#991b1b' if decision=='REJECTED' else '#92400e'}">
                {result.get('decision_explanation', '')}
              </div>
            </div>
            """, unsafe_allow_html=True)

            # Metrics row
            st.markdown(f"""
            <div class="metric-row">
              <div class="metric-box">
                <div class="metric-label">Request ID</div>
                <div class="metric-value" style="font-size:0.9rem;font-family:'DM Mono',monospace">{result.get('request_id','')}</div>
              </div>
              <div class="metric-box">
                <div class="metric-label">Stage</div>
                <div class="metric-value" style="font-size:0.9rem"><span class="stage-pill">{stage}</span></div>
              </div>
              <div class="metric-box">
                <div class="metric-label">Retries</div>
                <div class="metric-value">{result.get('retry_count', 0)}</div>
              </div>
              <div class="metric-box">
                <div class="metric-label">Status</div>
                <div class="metric-value" style="font-size:0.9rem">{result.get('status','')}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # AI review block
            if result.get("ai_review"):
                ai = result["ai_review"]
                conf_pct = int(ai["confidence"] * 100)
                st.markdown(f"""
                <div class="ai-card">
                  <h4>🤖 AI Review Agent Output</h4>
                  <div class="ai-label">Recommendation</div>
                  <div class="ai-value"><b>{ai['recommendation']}</b></div>
                  <div class="ai-label">Confidence</div>
                  <div class="conf-track"><div class="conf-fill" style="width:{conf_pct}%"></div></div>
                  <div class="ai-value" style="margin-top:-6px">{conf_pct}%</div>
                  <div class="ai-label">Explanation</div>
                  <div class="ai-value">{ai['explanation']}</div>
                  <div class="ai-label">Next Step</div>
                  <div class="ai-value">{ai['next_step']}</div>
                </div>
                """, unsafe_allow_html=True)

            # Save to session for audit link
            st.session_state["last_request_id"] = result.get("request_id", "")
            st.info(f"💡 View full audit trail in the **Audit Trail** page — Request ID: `{result.get('request_id','')}`")


# ── Page: Check Status ─────────────────────────────────────────────────────────
elif page == "🔍 Check Status":
    st.markdown("""
    <div class="top-bar">
      <h1>🔍 Application Status</h1>
      <span>Look up any application by Request ID</span>
    </div>
    """, unsafe_allow_html=True)

    default_id = st.session_state.get("last_request_id", "")
    rid = st.text_input("Request ID", value=default_id, placeholder="LOAN-XXXXXX")

    if st.button("🔎 Look Up", type="primary") and rid:
        result, status = api("GET", f"/applications/{rid}")

        if status == 404:
            st.error(f"Application `{rid}` not found.")
        elif "error" in result:
            st.error(result["error"])
        else:
            decision = result.get("final_decision", "")
            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(f"""
                <div class="card">
                  <h3>Application Overview</h3>
                  <div class="metric-row">
                    <div class="metric-box">
                      <div class="metric-label">Decision</div>
                      <div style="margin-top:6px">{decision_badge(decision)}</div>
                    </div>
                    <div class="metric-box">
                      <div class="metric-label">Current Stage</div>
                      <div style="margin-top:6px"><span class="stage-pill">{result.get('current_stage','')}</span></div>
                    </div>
                    <div class="metric-box">
                      <div class="metric-label">Retries</div>
                      <div class="metric-value">{result.get('retry_count', 0)}</div>
                    </div>
                  </div>
                  <div class="ai-label">Explanation</div>
                  <div class="ai-value" style="margin-top:4px">{result.get('decision_explanation','—')}</div>
                  <div class="ai-label" style="margin-top:8px">Created</div>
                  <div class="ai-value">{fmt_ts(result.get('created_at',''))}</div>
                  <div class="ai-label">Last Updated</div>
                  <div class="ai-value">{fmt_ts(result.get('updated_at',''))}</div>
                </div>
                """, unsafe_allow_html=True)

            with col2:
                if result.get("ai_review"):
                    ai = result["ai_review"]
                    conf_pct = int(ai["confidence"] * 100)
                    st.markdown(f"""
                    <div class="ai-card">
                      <h4>🤖 AI Review</h4>
                      <div class="ai-label">Recommendation</div>
                      <div class="ai-value"><b>{ai['recommendation']}</b></div>
                      <div class="ai-label">Confidence</div>
                      <div class="conf-track"><div class="conf-fill" style="width:{conf_pct}%"></div></div>
                      <div class="ai-value">{conf_pct}%</div>
                      <div class="ai-label">Explanation</div>
                      <div class="ai-value" style="font-size:0.82rem">{ai['explanation']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="card" style="text-align:center;color:#94a3b8;padding:40px 20px">
                      <div style="font-size:2rem">🔍</div>
                      <div style="font-size:0.85rem;margin-top:8px">No AI review — deterministic decision</div>
                    </div>
                    """, unsafe_allow_html=True)


# ── Page: Audit Trail ──────────────────────────────────────────────────────────
elif page == "📜 Audit Trail":
    st.markdown("""
    <div class="top-bar">
      <h1>📜 Audit Trail</h1>
      <span>Full timestamped event log for any application</span>
    </div>
    """, unsafe_allow_html=True)

    default_id = st.session_state.get("last_request_id", "")
    rid = st.text_input("Request ID", value=default_id, placeholder="LOAN-XXXXXX")

    if st.button("📜 Load Audit Trail", type="primary") and rid:
        result, status = api("GET", f"/applications/{rid}/audit")

        if status == 404:
            st.error(f"Application `{rid}` not found.")
        elif "error" in result:
            st.error(result["error"])
        else:
            trail = result.get("audit_trail", [])
            st.markdown(f"""
            <div style="display:flex;gap:16px;margin-bottom:16px;align-items:center">
              <div>{decision_badge(result.get('final_decision',''))}</div>
              <span class="stage-pill">{result.get('current_stage','')}</span>
              <span style="font-size:0.82rem;color:#64748b">{len(trail)} events recorded</span>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<h3>Event Timeline</h3>', unsafe_allow_html=True)

            for event in trail:
                details_str = ""
                if event.get("details"):
                    details_str = f'<div style="font-size:0.75rem;font-family:\'DM Mono\',monospace;color:#94a3b8;margin-top:3px;word-break:break-all">{json.dumps(event["details"], ensure_ascii=False)[:180]}</div>'

                st.markdown(f"""
                <div class="audit-row">
                  <div class="audit-time">{fmt_ts(event['timestamp'])}</div>
                  <div>
                    <span class="audit-stage">{event['stage']}</span>
                    <div class="audit-event" style="margin-top:4px">{event['event']}</div>
                    {details_str}
                  </div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)


# ── Page: Config & Rules ───────────────────────────────────────────────────────
elif page == "⚙️ Config & Rules":
    st.markdown("""
    <div class="top-bar">
      <h1>⚙️ Configuration & Rules</h1>
      <span>Live config — edit config.json and hot-reload</span>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        cfg, _ = api("GET", "/config/rules")

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<h3>Business Rules</h3>', unsafe_allow_html=True)

        if "rules" in cfg:
            for rule in sorted(cfg["rules"], key=lambda r: r.get("priority", 99)):
                action_color = "#fee2e2" if rule.get("action") == "REJECT" else "#d1fae5"
                action_text  = "#991b1b" if rule.get("action") == "REJECT" else "#065f46"
                st.markdown(f"""
                <div style="background:#f8fafc;border-radius:8px;padding:12px;margin-bottom:8px;border-left:3px solid {'#f87171' if rule['action']=='REJECT' else '#34d399'}">
                  <div style="display:flex;justify-content:space-between;align-items:center">
                    <span style="font-weight:600;color:#1e293b;font-size:0.9rem">{rule['name'].replace('_',' ').title()}</span>
                    <span style="background:{action_color};color:{action_text};border-radius:99px;padding:2px 10px;font-size:0.75rem;font-weight:700">{rule['action']}</span>
                  </div>
                  <div style="font-size:0.78rem;color:#64748b;margin-top:4px">{rule['description']}</div>
                  <div style="font-family:'DM Mono',monospace;font-size:0.72rem;color:#94a3b8;margin-top:6px">
                    P{rule.get('priority','?')} · {rule['field']} {rule['operator']} {rule['value']}
                    {'· derived' if rule.get('derived') else ''}
                  </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<h3>Workflow Settings</h3>', unsafe_allow_html=True)

        if "workflow" in cfg:
            wf = cfg["workflow"]
            t  = wf.get("ambiguous_thresholds", {})
            st.markdown(f"""
            <div style="line-height:2.2;font-size:0.88rem;color:#334155">
              <div><span style="color:#64748b;font-size:0.75rem">MAX RETRIES</span> &nbsp;&nbsp; <b>{wf.get('max_retries', '—')}</b></div>
              <div><span style="color:#64748b;font-size:0.75rem">RETRY DELAY</span> &nbsp;&nbsp; <b>{wf.get('retry_delay_seconds', '—')}s</b></div>
              <hr style="border:none;border-top:1px solid #f1f5f9;margin:10px 0">
              <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#94a3b8;margin-bottom:6px">AI Review Triggers</div>
              <div>Credit Score &nbsp;<b>{t.get('credit_score_min','?')} – {t.get('credit_score_max','?')}</b></div>
              <div>Income &nbsp;<b>${t.get('income_min',0):,} – ${t.get('income_max',0):,}</b></div>
              <div>Missing Docs &nbsp;<b>Always</b></div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<h3>Raw Config JSON</h3>', unsafe_allow_html=True)
        st.code(json.dumps(cfg, indent=2), language="json")

        if st.button("🔄 Hot-Reload Config", type="secondary", use_container_width=True):
            res, code = api("POST", "/config/reload")
            if code == 200:
                st.success(f"✅ Reloaded — {res.get('rules_count', '?')} rules loaded")
            else:
                st.error("Reload failed")

        st.markdown("</div>", unsafe_allow_html=True)


# ── Page: Manual Override ──────────────────────────────────────────────────────
elif page == "🛡️ Manual Override":
    st.markdown("""
    <div class="top-bar">
      <h1>🛡️ Manual Override</h1>
      <span>Override applications stuck in MANUAL_REVIEW or FAILED</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="card" style="border-left:4px solid #f59e0b">
      <div style="font-size:0.82rem;color:#92400e">
        ⚠️ <b>Operator action</b> — This permanently overrides the workflow decision and is recorded in the audit log.
        Only applications in <code>MANUAL_REVIEW</code> or <code>FAILED</code> stage can be overridden.
      </div>
    </div>
    """, unsafe_allow_html=True)

    rid      = st.text_input("Request ID", placeholder="LOAN-XXXXXX")
    decision = st.radio("Override Decision", ["APPROVED", "REJECTED"], horizontal=True)
    reason   = st.text_area("Reason (required)", placeholder="e.g. Verified income documents manually. Applicant confirmed employment.")

    if st.button("⚡ Apply Override", type="primary") and rid and reason.strip():
        result, status = api(
            "POST",
            f"/applications/{rid}/override",
            params={"decision": decision, "reason": reason},
        )

        if status == 200:
            st.success(f"✅ Application `{rid}` has been manually **{decision}**.")
            st.markdown(f"""
            <div class="card">
              <div class="ai-label">Result</div>
              <div class="ai-value"><b>{result.get('final_decision','')}</b></div>
              <div class="ai-label">Message</div>
              <div class="ai-value">{result.get('message','')}</div>
            </div>
            """, unsafe_allow_html=True)
        elif status == 404:
            st.error(f"Application `{rid}` not found.")
        else:
            st.error(result.get("detail", "Override failed."))
    elif st.button("⚡ Apply Override", type="primary", key="override_guard"):
        st.warning("Please fill in both the Request ID and a reason.")