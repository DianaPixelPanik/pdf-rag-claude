import streamlit as st
import json
import os
import re
from datetime import datetime, timezone, date
from html import escape
from PyPDF2 import PdfReader
import anthropic
from dotenv import load_dotenv

load_dotenv()

AUDIT_LOG_PATH = "audit.jsonl"

PROFILE_FIELDS = {
    "full_name":           "Full name",
    "date_of_birth":       "Date of birth",
    "nationality":         "Nationality",
    "country_of_residence":"Country of residence",
    "address":             "Residential address",
    "phone":               "Phone",
    "email":               "Email",
    "document_type":       "ID type",
    "document_number":     "Document number",
    "document_expiry":     "Document expiry",
    "occupation":          "Occupation",
    "employer":            "Employer",
    "source_of_funds":     "Source of funds",
    "pep_status":          "PEP status",
    "account_purpose":     "Account purpose",
}

REQUIRED_FIELDS = list(PROFILE_FIELDS.keys())

SYSTEM_PROMPT = """You are a KYC (Know Your Customer) compliance officer at a financial institution. \
You conduct client onboarding interviews: professional, warm, concise.

Collect ALL of these fields through natural conversation — one question at a time:
  full_name, date_of_birth, nationality, country_of_residence, address, phone, email,
  document_type, document_number, document_expiry, occupation, employer,
  source_of_funds, pep_status, account_purpose

Field notes:
- date_of_birth: DD/MM/YYYY
- address: street + city + postcode + country
- source_of_funds: salary / business income / investments / inheritance / other
- pep_status: yes or no; if yes ask for role description
- account_purpose: what the client intends to use the account/service for

ALWAYS respond with ONLY valid JSON — no prose, no markdown fences:
{
  "message": "your message to the client",
  "extracted": {"field_name": "value"},
  "needs_document": "id" | "proof_of_address" | null,
  "status": "ongoing" | "complete"
}

Rules:
1. Ask ONE question per turn.
2. Extract every piece of information the client volunteers into "extracted".
3. Acknowledge the client's answer before asking the next question.
4. When asking for identity document details, set needs_document to "id".
5. After confirming the residential address, set needs_document to "proof_of_address".
6. Set status "complete" only when ALL 15 fields are collected.
7. If info seems inconsistent, note it tactfully in your message."""

CSS = """
<style>
    [data-testid="stDeployButton"] {display:none;}
    [data-testid="stStatusWidget"]  {display:none;}
    [data-testid="stToolbar"]       {display:none;}
    header {visibility:hidden;}
    #MainMenu {visibility:hidden;}

    .bubble {
        padding: 0.85rem 1.1rem;
        border-radius: 10px;
        margin-bottom: 0.55rem;
        display: flex;
        align-items: flex-start;
        gap: 0.65rem;
    }
    .bubble.agent { background:#1c2535; border-left:3px solid #4caf7d; }
    .bubble.user  { background:#18202e; border-left:3px solid #4a90d9; }
    .bubble.doc   { background:#1a1f30; border-left:3px solid #f0a040; }
    .blabel {
        font-size:.67rem; font-weight:700;
        letter-spacing:.08em; text-transform:uppercase;
        min-width:40px; padding-top:3px;
    }
    .blabel.a { color:#4caf7d; }
    .blabel.u { color:#4a90d9; }
    .blabel.d { color:#f0a040; }
    .btext { color:#dde1e7; font-size:.93rem; line-height:1.65; flex:1; }

    .prow {
        display:flex; justify-content:space-between;
        padding:.22rem 0; border-bottom:1px solid #222b3a;
        font-size:.8rem;
    }
    .plabel { color:#6a778f; }
    .pval   { color:#cdd3de; font-weight:500; max-width:58%; text-align:right; word-break:break-word; }
    .pempty { color:#2e3a4a; font-style:italic; }

    .badge {
        display:inline-block; padding:2px 9px; border-radius:10px;
        font-size:.72rem; font-weight:700; letter-spacing:.03em;
        white-space:nowrap;
    }
    .badge.ok      { background:#0d2e1a; color:#4caf7d; }
    .badge.warn    { background:#2e2508; color:#f0c040; }
    .badge.fail    { background:#2e0e0e; color:#e05555; }
    .badge.pending { background:#1a2030; color:#6a778f; }

    .srow {
        display:flex; justify-content:space-between; align-items:center;
        padding:.28rem 0; border-bottom:1px solid #1a2235; font-size:.8rem;
    }
    .srow-label { color:#8896aa; }

    .review-card {
        background:#151d2b; border:1px solid #243047;
        border-radius:10px; padding:1.1rem 1.4rem; margin-bottom:0.8rem;
    }
    .review-card h4 { color:#8896aa; font-size:.75rem; letter-spacing:.06em;
        text-transform:uppercase; margin:0 0 .6rem 0; }
    .review-row {
        display:flex; justify-content:space-between; align-items:center;
        padding:.3rem 0; border-bottom:1px solid #1e2a3a; font-size:.88rem;
    }
    .review-row:last-child { border-bottom:none; }
    .review-row-label { color:#8896aa; }
</style>
"""


# ── helpers ──────────────────────────────────────────────────────────────────

def write_audit(entry: dict):
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def extract_pdf_text(uploaded_file) -> str:
    reader = PdfReader(uploaded_file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def build_user_turn(client_text: str, profile: dict) -> str:
    filled   = {k: v for k, v in profile.items() if v is not None}
    missing  = [PROFILE_FIELDS[k] for k in REQUIRED_FIELDS if profile.get(k) is None]
    snapshot = json.dumps(filled, ensure_ascii=False) if filled else "(empty)"
    gaps     = ", ".join(missing) if missing else "none — all collected"
    return (
        f"[Profile so far] {snapshot}\n"
        f"[Missing fields] {gaps}\n\n"
        f"[Client] {client_text}"
    )


def call_agent(api_messages: list, api_key: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=api_messages,
        )
    except anthropic.AuthenticationError:
        st.error("Invalid API key. Check your key at console.anthropic.com and re-enter it in the sidebar.")
        st.stop()
    except anthropic.APIConnectionError:
        st.error("Connection error. Check your internet connection and try again.")
        st.stop()
    except anthropic.RateLimitError:
        st.error("Rate limit reached. Wait a moment and try again.")
        st.stop()
    except anthropic.APIStatusError as e:
        st.error(f"API error {e.status_code}: {e.message}")
        st.stop()

    raw = resp.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        return {"message": raw, "extracted": {}, "needs_document": None, "status": "ongoing"}


def completeness(profile: dict) -> float:
    return sum(1 for v in profile.values() if v is not None) / len(REQUIRED_FIELDS)


def parse_date(s: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def compute_review_statuses(profile: dict) -> dict:
    today = datetime.now().date()

    # Document verification
    expiry_raw = profile.get("document_expiry")
    if not expiry_raw:
        doc = ("pending", "Pending")
    else:
        exp = parse_date(expiry_raw)
        if exp is None:
            doc = ("warn", "Check required")
        elif exp < today:
            doc = ("fail", f"Expired {(today - exp).days}d ago")
        elif (exp - today).days < 90:
            doc = ("warn", f"Expires in {(exp - today).days}d")
        else:
            doc = ("ok", "Valid")

    # PEP review
    pep_raw = (profile.get("pep_status") or "").lower()
    if not pep_raw:
        pep = ("pending", "Pending")
    elif any(w in pep_raw for w in ("yes", "да", "true")):
        pep = ("fail", "Required")
    else:
        pep = ("ok", "Cleared")

    # Risk review — manual gate; elevated automatically on fail flags
    if pep[0] == "fail" or doc[0] == "fail":
        risk = ("warn", "Elevated — manual review")
    elif completeness(profile) == 1.0:
        risk = ("pending", "Pending")
    else:
        risk = ("pending", "—")

    return {"document_verification": doc, "pep_review": pep, "risk_review": risk}


def badge(level: str, text: str) -> str:
    return f'<span class="badge {level}">{escape(text)}</span>'


# ── UI components ─────────────────────────────────────────────────────────────

def render_sidebar(profile: dict):
    pct = completeness(profile)
    st.sidebar.markdown("### Client Profile")
    st.sidebar.progress(pct, text=f"Profile completeness: {int(pct * 100)}%")
    st.sidebar.markdown("")

    # review statuses
    statuses = compute_review_statuses(profile)
    STATUS_LABELS = {
        "document_verification": "Document verification",
        "pep_review":            "PEP review",
        "risk_review":           "Risk review",
    }
    for key, label in STATUS_LABELS.items():
        lvl, text = statuses[key]
        st.sidebar.markdown(
            f'<div class="srow"><span class="srow-label">{label}</span>'
            f'{badge(lvl, text)}</div>',
            unsafe_allow_html=True,
        )
    st.sidebar.markdown("")

    for key, label in PROFILE_FIELDS.items():
        val = profile.get(key)
        if val:
            st.sidebar.markdown(
                f'<div class="prow"><span class="plabel">{label}</span>'
                f'<span class="pval">{escape(str(val))}</span></div>',
                unsafe_allow_html=True,
            )
        else:
            st.sidebar.markdown(
                f'<div class="prow"><span class="plabel">{label}</span>'
                f'<span class="pempty">—</span></div>',
                unsafe_allow_html=True,
            )

    if pct == 1.0:
        st.sidebar.markdown("---")
        st.sidebar.download_button(
            "Export profile (JSON)",
            data=json.dumps(profile, ensure_ascii=False, indent=2),
            file_name=f"kyc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
        )


def render_chat(history: list):
    for msg in history:
        role = msg["role"]
        text = escape(msg["content"])
        if role == "agent":
            st.markdown(
                f'<div class="bubble agent"><span class="blabel a">KYC</span>'
                f'<span class="btext">{text}</span></div>',
                unsafe_allow_html=True,
            )
        elif role == "user":
            st.markdown(
                f'<div class="bubble user"><span class="blabel u">You</span>'
                f'<span class="btext">{text}</span></div>',
                unsafe_allow_html=True,
            )
        elif role == "document":
            st.markdown(
                f'<div class="bubble doc"><span class="blabel d">Doc</span>'
                f'<span class="btext">{text}</span></div>',
                unsafe_allow_html=True,
            )


# ── interview logic ───────────────────────────────────────────────────────────

def apply_result(result: dict):
    for field, value in result.get("extracted", {}).items():
        if field in st.session_state.profile and value:
            st.session_state.profile[field] = value
    if result.get("needs_document"):
        doc = result["needs_document"]
        if doc not in st.session_state.docs_uploaded:
            st.session_state.pending_doc = doc
    if result.get("status") == "complete":
        st.session_state.status = "complete"


def agent_turn(client_text: str, api_key: str):
    turn = build_user_turn(client_text, st.session_state.profile)
    st.session_state.api_msgs.append({"role": "user", "content": turn})

    with st.spinner(""):
        result = call_agent(st.session_state.api_msgs, api_key)

    st.session_state.api_msgs.append({"role": "assistant", "content": json.dumps(result)})
    st.session_state.history.append({"role": "agent", "content": result["message"]})
    apply_result(result)
    return result


def start_interview(api_key: str):
    result = agent_turn("Hello, I would like to complete my onboarding.", api_key)
    write_audit({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "interview_start",
    })
    # remove the auto-greeting from visible history (keep only agent reply)
    st.session_state.history = [h for h in st.session_state.history if h["role"] == "agent"]
    return result


def handle_message(text: str, api_key: str):
    st.session_state.history.append({"role": "user", "content": text})
    result = agent_turn(text, api_key)

    write_audit({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "turn",
        "client": text,
        "agent": result["message"],
        "extracted": result.get("extracted", {}),
        "profile": dict(st.session_state.profile),
    })

    if st.session_state.status == "complete":
        statuses = compute_review_statuses(st.session_state.profile)
        write_audit({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "interview_complete",
            "profile": dict(st.session_state.profile),
            "review_statuses": {k: v[1] for k, v in statuses.items()},
        })


def handle_document(doc_type: str, uploaded, api_key: str):
    text = extract_pdf_text(uploaded)[:3000]
    note = f"{uploaded.name} uploaded ({len(text)} chars extracted)"
    st.session_state.history.append({"role": "document", "content": note})

    label = "identity document" if doc_type == "id" else "proof of address"
    result = agent_turn(
        f"I have uploaded my {label}. Document content:\n\n{text}",
        api_key,
    )

    st.session_state.docs_uploaded.add(doc_type)
    st.session_state.pending_doc = None

    write_audit({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "document_upload",
        "doc_type": doc_type,
        "filename": uploaded.name,
        "extracted": result.get("extracted", {}),
    })


# ── main ─────────────────────────────────────────────────────────────────────

def init_state():
    defaults = {
        "profile":       {k: None for k in REQUIRED_FIELDS},
        "history":       [],
        "api_msgs":      [],
        "status":        "ongoing",
        "pending_doc":   None,
        "docs_uploaded": set(),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def main():
    st.set_page_config(page_title="KYC Onboarding", page_icon=None, layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()

    # ── sidebar ──
    with st.sidebar:
        api_key = (
            os.getenv("ANTHROPIC_API_KEY")
            or st.secrets.get("ANTHROPIC_API_KEY", "")
        )
        if not api_key:
            raw = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-...")
            api_key = raw.strip().encode("ascii", "ignore").decode("ascii")
        else:
            st.caption("API key loaded from environment.")

        st.markdown("---")
        render_sidebar(st.session_state.profile)
        st.markdown("---")
        if st.button("Restart", use_container_width=True):
            for k in ["profile", "history", "api_msgs", "status", "pending_doc", "docs_uploaded"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── main area ──
    st.markdown("## KYC Onboarding")

    if not api_key:
        st.info("Enter your Anthropic API key in the sidebar to begin.")
        return

    if not st.session_state.history:
        start_interview(api_key)
        st.rerun()

    render_chat(st.session_state.history)

    # document upload prompt
    pending = st.session_state.pending_doc
    if pending and pending not in st.session_state.docs_uploaded:
        label = "Identity Document (passport / national ID)" if pending == "id" else "Proof of Address"
        st.markdown(f"**Document required: {label}**")
        uploaded = st.file_uploader(f"Upload {label} (PDF)", type=["pdf"], key=f"up_{pending}")
        if uploaded:
            handle_document(pending, uploaded, api_key)
            st.rerun()

    # chat input / completion card
    if st.session_state.status == "complete":
        st.markdown("---")
        statuses = compute_review_statuses(st.session_state.profile)
        rows = {
            "Profile completeness":   ("ok",                       "100%"),
            "Document verification":  statuses["document_verification"],
            "PEP review":             statuses["pep_review"],
            "Risk review":            statuses["risk_review"],
        }
        rows_html = "".join(
            f'<div class="review-row">'
            f'<span class="review-row-label">{label}</span>'
            f'{badge(lvl, text)}'
            f'</div>'
            for label, (lvl, text) in rows.items()
        )
        st.markdown(
            f'<div class="review-card"><h4>Onboarding Summary</h4>{rows_html}</div>',
            unsafe_allow_html=True,
        )
    else:
        user_input = st.chat_input("Your answer...")
        if user_input:
            handle_message(user_input, api_key)
            st.rerun()


if __name__ == "__main__":
    main()
