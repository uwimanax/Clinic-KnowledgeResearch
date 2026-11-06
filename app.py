from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

import streamlit as st

import babycare_engine as be

st.set_page_config(
    page_title="BabyCare AI",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
:root {
  --ink: #12343b;
  --muted: #5b7c8a;
  --teal: #0f7c8c;
  --line: #d8eaf1;
  --soft: #eef8fb;
  --white: #ffffff;
}
.stApp {
  background: linear-gradient(180deg, #f7fbfd 0%, #ffffff 38%);
  color: var(--ink);
}
[data-testid="stSidebar"] {
  background: var(--soft);
  border-right: 1px solid var(--line);
}
h1, h2, h3, h4 {
  color: var(--ink);
  letter-spacing: -0.02em;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 1rem 1.1rem;
  box-shadow: 0 8px 24px rgba(18, 52, 59, 0.05);
}
.bc-hero {
  background: linear-gradient(135deg, #e8f7fa 0%, #ffffff 72%);
  border: 1px solid var(--line);
  border-radius: 24px;
  padding: 1.6rem 1.7rem;
  margin-bottom: 1.1rem;
}
.bc-hero h1 {
  margin: 0 0 0.3rem 0;
  font-size: 2.05rem;
}
.bc-kicker {
  text-transform: uppercase;
  letter-spacing: 0.13em;
  font-size: 0.72rem;
  color: var(--teal);
  font-weight: 700;
  margin-bottom: 0.55rem;
}
.bc-muted {
  color: var(--muted);
}
.bc-banner {
  border-radius: 18px;
  padding: 1.1rem 1.2rem;
  margin: 0.4rem 0 1rem 0;
  border: 1px solid var(--line);
  background: var(--soft);
}
.bc-banner strong {
  display: block;
  font-size: 1.25rem;
  margin-bottom: 0.25rem;
}
.bc-emergency {
  background: #fff1f1;
  border-color: #f0b7b7;
  color: #7f1d1d;
}
.bc-urgent {
  background: #fff8e8;
  border-color: #f0d39a;
  color: #6d4b0c;
}
.bc-routine {
  background: #edfafa;
  border-color: #b9e3e3;
  color: #0b5f68;
}
.bc-pill {
  display: inline-block;
  padding: 0.24rem 0.62rem;
  border-radius: 999px;
  background: var(--soft);
  border: 1px solid var(--line);
  margin: 0.15rem 0.15rem 0.15rem 0;
  font-size: 0.8rem;
}
.bc-small {
  font-size: 0.86rem;
  color: var(--muted);
}
.bc-section {
  margin: 1.1rem 0 0.45rem 0;
}
.bc-section h3 {
  margin: 0;
  font-size: 1.18rem;
}
.bc-section p {
  margin: 0.15rem 0 0 0;
  color: var(--muted);
  font-size: 0.9rem;
}
div.stButton > button,
div.stDownloadButton > button {
  border-radius: 12px;
  border: 1px solid #b9dce5;
  background: #ffffff;
  color: var(--ink);
}
div.stButton > button[kind="primary"],
div.stFormSubmitButton > button[kind="primary"] {
  background: var(--teal);
  border-color: var(--teal);
  color: #ffffff;
}
.st-key-babycare_launcher {
  position: fixed !important;
  right: 1.5rem !important;
  bottom: 1.5rem !important;
  z-index: 1000000 !important;
  width: auto !important;
}
.st-key-babycare_launcher .stButton > button {
  border-radius: 999px;
  padding: 0.65rem 1.15rem;
  box-shadow: 0 12px 30px rgba(18, 52, 59, 0.18);
}
.st-key-chat_page {
  max-width: 960px;
  margin: 0 auto;
  padding-bottom: 4rem;
}
.st-key-chat_page div[data-testid="stChatInput"] {
  max-width: 960px;
  margin: 0 auto;
}
.bc-chat-hero {
  background: linear-gradient(135deg, #e8f7fa 0%, #ffffff 72%);
  border: 1px solid var(--line);
  border-radius: 24px;
  padding: 1.5rem 1.6rem;
  margin-bottom: 1.1rem;
}
.bc-chat-hero h1 {
  margin: 0 0 0.35rem 0;
  font-size: 1.85rem;
}
.bc-chat-hero p {
  margin: 0;
  max-width: 680px;
}
.bc-chat-urgency {
  background: var(--white);
  border: 1px solid var(--line);
  border-left: 4px solid var(--teal);
  border-radius: 16px;
  padding: 1rem 1.15rem;
  margin: 0.4rem 0 0.9rem 0;
}
.bc-chat-urgency.is-emergency {
  border-left-color: #b42318;
}
.bc-chat-urgency.is-urgent {
  border-left-color: #b7791f;
}
.bc-chat-urgency strong {
  display: block;
  font-size: 1.12rem;
  margin-bottom: 0.25rem;
  color: var(--ink);
}
.bc-chat-note {
  background: var(--soft);
  border: 1px solid var(--line);
  border-left: 4px solid var(--teal);
  border-radius: 16px;
  padding: 0.9rem 1.05rem;
  margin: 0.8rem 0 0.4rem 0;
  color: var(--ink);
  font-size: 0.92rem;
}
.bc-chat-summary {
  color: var(--muted);
  font-size: 0.9rem;
  margin: 0.15rem 0 0.75rem 0;
}
"""

st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def _escape(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _float_or_none(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@st.cache_resource(show_spinner="Building the local retrieval index...")
def _store_for(corpus_path: str, mtime_ns: int, size: int):
    chunks = be.load_corpus(corpus_path)
    if not chunks:
        return None
    return be.TfidfVectorStore(chunks)


def get_store():
    path = Path(be.CORPUS_PATH)
    if not path.exists():
        return None
    stat = path.stat()
    return _store_for(str(path), stat.st_mtime_ns, stat.st_size)


def _section(kicker: str, title: str, description: str) -> None:
    st.markdown(
        '<div class="bc-section">'
        f'<div class="bc-kicker">{_escape(kicker)}</div>'
        f"<h3>{_escape(title)}</h3>"
        f"<p>{_escape(description)}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_sidebar(store) -> None:
    with st.sidebar:
        st.markdown("## BabyCare AI")
        st.write("Local pediatric decision support for children aged 0 to 60 months.")
        st.write("Evidence is retrieved from the indexed guideline documents in this project.")
        if st.button("Download / refresh and index documents", width="stretch"):
            with st.spinner("Downloading and indexing the guideline corpus..."):
                try:
                    download_report, ingestion_report = be.build_corpus()
                except Exception as exc:
                    st.error(f"Ingestion failed: {exc}")
                else:
                    _store_for.clear()
                    indexed = sum(1 for row in ingestion_report if row.get("status") == "OK")
                    chunks = sum(int(row.get("chunks") or 0) for row in ingestion_report)
                    st.success(f"Indexed {indexed} documents and {chunks} text chunks.")
                    failures = [row for row in download_report if row.get("status") != "OK"]
                    if failures:
                        st.caption(f"{len(failures)} source download(s) did not complete. See the ingestion report.")
        if store is not None and store.available:
            documents = {chunk.get("doc_id") for chunk in store.chunks}
            st.caption(f"Indexed documents: {len(documents)}. Text chunks: {len(store.chunks)}.")
        else:
            st.caption("No local document index is loaded yet.")
        st.divider()
        st.caption("This tool supports, but does not replace, clinician assessment.")


CHAT_GREETING = (
    "Hi, I'm the BabyCare helper. Tell me your child's age and what you're noticing, "
    "for example: \"My 18 month old has a fever and a cough.\" I'll search pediatric "
    "guidelines and share possible explanations, urgency, and next steps. I cannot diagnose. "
    "If this is an emergency, call your local emergency number now."
)

CHAT_SYMPTOM_KEYWORDS = {
    "fever": ["fever", "feverish", "high temperature", "hot to touch"],
    "cough": ["cough", "coughing"],
    "difficulty_breathing": [
        "difficulty breathing",
        "trouble breathing",
        "struggling to breathe",
        "breathing hard",
        "breathless",
        "wheezing",
        "wheeze",
    ],
    "fast_breathing": ["fast breathing", "breathing fast", "rapid breathing", "breathing quickly"],
    "vomiting": ["vomit", "vomiting", "throwing up", "threw up"],
    "diarrhea": ["diarrhea", "diarrhoea", "loose stool", "loose stools", "watery stool"],
    "constipation": ["constipation", "constipated", "hard stool"],
    "abdominal_pain": ["abdominal pain", "stomach pain", "tummy pain", "belly pain"],
    "poor_feeding": [
        "poor feeding",
        "not feeding",
        "not feeding well",
        "eating less",
        "not eating",
        "feeding less",
        "not drinking",
        "drinking less",
    ],
    "refusal_breastfeed": [
        "refusing breast",
        "refuses breast",
        "refusing to breastfeed",
        "will not breastfeed",
        "refusing feeds",
    ],
    "rash": ["rash", "spots", "hives"],
    "seizures": ["seizure", "seizures", "convulsion", "convulsions", "fit", "fits"],
    "excessive_crying": ["crying a lot", "excessive crying", "inconsolable"],
    "unusual_sleepiness": ["sleepy", "lethargic", "hard to wake", "drowsy"],
    "weakness": ["weak", "weakness", "floppy"],
    "dehydration": ["dehydrated", "dehydration", "dry mouth", "no urine", "sunken eyes"],
    "ear_pain": ["ear pain", "earache", "ear discharge", "pulling ear"],
    "jaundice": ["jaundice", "yellow skin", "yellow eyes"],
    "swelling": ["swelling", "swollen", "puffy"],
}

CHAT_DANGER_KEYWORDS = {
    "blue_lips": ["blue lips", "blue skin", "grey lips", "gray lips", "grey skin", "gray skin"],
    "unresponsive": ["unresponsive", "not responding", "will not wake", "wont wake", "hard to wake"],
    "unable_to_feed": ["unable to feed", "cannot feed", "cant feed", "not feeding at all", "refusing all feeds"],
    "shock": ["shock", "cold and clammy", "very pale", "limp"],
}


def _keywords_to_keys(text: str, mapping: dict[str, list[str]]) -> list[str]:
    lowered = text.lower()
    found = []
    for key, phrases in mapping.items():
        for phrase in phrases:
            match = re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", lowered)
            if not match:
                continue
            prefix = lowered[max(0, match.start() - 18) : match.start()]
            if re.search(r"\b(no|not|without|denies|deny|never)\s*$", prefix):
                continue
            found.append(key)
            break
    return found


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


AGE_PATTERN = re.compile(
    r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*"
    r"(days?|months?|years?|weeks?|d|mo|mos|m|yr|yrs|y|wk|wks|w|yo)\b",
    re.IGNORECASE,
)
AGE_UNIT_ALIASES = {
    "d": "days",
    "day": "days",
    "days": "days",
    "mo": "months",
    "mos": "months",
    "m": "months",
    "month": "months",
    "months": "months",
    "y": "years",
    "yr": "years",
    "yrs": "years",
    "yo": "years",
    "year": "years",
    "years": "years",
    "w": "weeks",
    "wk": "weeks",
    "wks": "weeks",
    "week": "weeks",
    "weeks": "weeks",
}


def _parse_age(text: str) -> tuple[float, str] | None:
    for match in AGE_PATTERN.finditer(text):
        prefix = text[max(0, match.start() - 12) : match.start()].lower()
        if re.search(r"\b(for|since|last|past)\s+$", prefix):
            continue
        value = float(match.group(1))
        unit = AGE_UNIT_ALIASES.get(match.group(2).lower(), "months")
        if value <= 0:
            continue
        if unit == "weeks":
            return value * 7, "days"
        return value, unit
    return None


def _chat_urgency(report: dict, age_months: float | None, symptoms: list[str]) -> tuple[str, list[str]]:
    urgency = report.get("urgency", {})
    emergency = list(urgency.get("emergency_reasons", []))
    urgent = list(urgency.get("urgent_reasons", []))
    if age_months is not None and age_months < 3 and "fever" in symptoms:
        emergency.append("Fever in a baby under 3 months needs an urgent same-day assessment.")
    if emergency:
        return "Emergency", emergency
    if urgent:
        return "Urgent", urgent
    return "Routine", []


def _chat_next_steps(level: str) -> list[str]:
    if level == "Emergency":
        steps = [
            "Call your local emergency number or go to the nearest emergency department now.",
            "Do not wait to see if things improve.",
        ]
    elif level == "Urgent":
        steps = [
            "Contact a doctor or clinic today.",
            "If you cannot reach one, or your child gets worse, go to the emergency department.",
        ]
    else:
        steps = [
            "Keep feeding and fluids going, and watch your child at home.",
            "Contact a clinician if you are worried or if symptoms change.",
        ]
    steps.append("A clinician should assess your child. This quick check is not a diagnosis.")
    return steps


def _chat_payload(
    report: dict,
    age_months: float | None,
    symptoms: list[str],
    danger_signs: list[str],
    age_label: str,
) -> dict:
    level, reasons = _chat_urgency(report, age_months, symptoms)
    diseases = report.get("diseases", [])
    conditions = []
    for disease in diseases[:4]:
        conditions.append(
            {
                "name": disease.get("name", ""),
                "why": disease.get("why_considered", []),
                "serious": bool(disease.get("serious")),
                "references": disease.get("references", [])[:3],
            }
        )
    sources = []
    if conditions:
        sources = conditions[0]["references"]
    if not sources:
        sources = report.get("references", [])[:3]
    unique_sources = []
    seen = set()
    for ref in sources:
        key = (ref.get("doc_id"), ref.get("page"))
        if key in seen:
            continue
        seen.add(key)
        unique_sources.append(
            {
                "organization": ref.get("organization", ""),
                "title": ref.get("title", ""),
                "page": ref.get("page", ""),
                "url": ref.get("url", ""),
            }
        )
    return {
        "level": level,
        "reasons": reasons[:4],
        "conditions": conditions,
        "next_steps": _chat_next_steps(level),
        "sources": unique_sources[:3],
        "age_months": age_months,
        "age_label": age_label,
        "symptoms": [be.SYMPTOM_LABELS.get(key, key) for key in symptoms],
        "red_flags": [be.DANGER_LABELS.get(key, key) for key in danger_signs],
    }


def _render_chat_result(payload: dict, show_header: bool = True) -> None:
    level = payload.get("level", "Routine")
    labels = {
        "Emergency": "Emergency: get help now",
        "Urgent": "Urgent: contact a clinician today",
        "Routine": "Routine: no red flags reported",
    }
    css = {"Emergency": "is-emergency", "Urgent": "is-urgent", "Routine": "is-routine"}.get(level, "")
    reasons = payload.get("reasons", [])
    reason_html = "<br>".join(_escape(reason) for reason in reasons)

    if show_header:
        st.markdown(
            '<div class="bc-section">'
            '<div class="bc-kicker">Guidance</div>'
            "<h3>Your quick check</h3>"
            "<p>Most relevant possibilities first, followed by what to do next.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    summary = []
    if payload.get("age_label"):
        summary.append(f"Age: {payload['age_label']}")
    if payload.get("symptoms"):
        summary.append("Symptoms: " + ", ".join(payload["symptoms"]))
    if payload.get("red_flags"):
        summary.append("Red flags: " + ", ".join(payload["red_flags"]))
    if summary:
        st.markdown(f'<div class="bc-chat-summary">{_escape(" | ".join(summary))}</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="bc-chat-urgency {css}">'
        f'<div class="bc-kicker">Urgency</div><strong>{_escape(labels.get(level, level))}</strong>'
        f'<div>{reason_html or "No warning signs were reported in this quick check."}</div>'
        "</div>",
        unsafe_allow_html=True,
    )

    conditions = payload.get("conditions", [])
    st.markdown("### Possible explanations")
    st.caption("These are possibilities from the guideline search, not a diagnosis.")
    if conditions:
        for index, condition in enumerate(conditions[:3], start=1):
            with st.container(border=True):
                left, right = st.columns([4, 1], vertical_alignment="center")
                left.markdown(f"#### {index}. {condition.get('name', '')}")
                if condition.get("serious"):
                    right.markdown('<span class="bc-pill">Worth checking soon</span>', unsafe_allow_html=True)
                why = condition.get("why", [])
                st.markdown("**Why it is on the list**")
                st.write(", ".join(why) if why else "It matched the age and symptoms you shared.")
        if len(conditions) > 3:
            with st.expander("Other possibilities considered"):
                for condition in conditions[3:]:
                    st.write(condition.get("name", ""))
    else:
        st.info("No guideline-matched explanation was found for these symptoms. That does not mean nothing is wrong.")

    with st.container(border=True):
        st.markdown("### What to do next")
        for index, step in enumerate(payload.get("next_steps", []), start=1):
            st.markdown(f"**{index}.** {step}")

    st.markdown(
        '<div class="bc-chat-note">'
        "<strong>Seek emergency care now if you see:</strong> blue or grey lips, struggling to breathe, "
        "unresponsiveness, a seizure, or your child cannot feed."
        "</div>",
        unsafe_allow_html=True,
    )

    sources = payload.get("sources", [])
    if sources:
        with st.expander("Guideline sources"):
            for source in sources:
                label = " | ".join(
                    value for value in (source.get("organization"), source.get("title")) if value
                )
                if source.get("page"):
                    label += f" | page {source['page']}"
                if source.get("url"):
                    st.markdown(f"- [{_escape(label)}]({source['url']})")
                else:
                    st.markdown(f"- {_escape(label)}")
    st.caption("Only the information you entered was used. This does not replace a clinician.")


def render_chat_launcher() -> None:
    with st.container(key="babycare_launcher"):
        if st.button("Ask BabyCare", key="chat_launcher", type="primary"):
            st.session_state["chat_open"] = True
            st.rerun()


def _empty_chat_context() -> dict:
    return {"age_value": None, "age_unit": "months", "symptoms": [], "danger_signs": []}


def _ensure_chat_state() -> None:
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = [{"role": "assistant", "text": CHAT_GREETING}]
    if "chat_context" not in st.session_state:
        st.session_state["chat_context"] = _empty_chat_context()


def _reset_chat() -> None:
    st.session_state["chat_messages"] = [{"role": "assistant", "text": CHAT_GREETING}]
    st.session_state["chat_context"] = _empty_chat_context()


def _append_chat(role: str, text: str = "", payload: dict | None = None) -> None:
    message = {"role": role, "text": text}
    if payload is not None:
        message["payload"] = payload
    st.session_state["chat_messages"].append(message)


def _chat_missing_info_reply(context: dict) -> str:
    has_age = context.get("age_value") is not None
    has_symptoms = bool(context.get("symptoms") or context.get("danger_signs"))
    if has_symptoms and not has_age:
        return (
            "Thanks, I have noted that. How old is your child? "
            "You can give the age in days, months, or years."
        )
    if has_age and not has_symptoms:
        return (
            "Thanks. What symptoms are you noticing? "
            "For example: fever, cough, vomiting, diarrhea, poor feeding, or a rash."
        )
    return "How old is your child, and what symptoms are you noticing?"


def _chat_run_guidance(store, context: dict) -> dict:
    age_value = context.get("age_value")
    age_unit = context.get("age_unit", "months")
    age_text = f"{age_value:g}"
    patient = {
        "age_value": age_text,
        "age_unit": age_unit,
        "sex": "Other / unknown",
        "symptoms": context.get("symptoms", []),
        "danger_signs": context.get("danger_signs", []),
        "vitals": {},
        "vitals_not_collected": [
            "temperature_c",
            "heart_rate",
            "respiratory_rate",
            "spo2",
            "bp_systolic",
        ],
    }
    validation = be.validate_patient(patient)
    if validation["errors"]:
        return {"role": "assistant", "text": " ".join(validation["errors"])}

    try:
        with st.spinner("Looking through pediatric guidelines..."):
            report = be.run_agents(patient, store, llm=be.LLMClient())
    except Exception as exc:
        return {"role": "assistant", "text": f"Guidance failed: {exc}"}

    payload = _chat_payload(
        report,
        report.get("profile", {}).get("age_months"),
        context.get("symptoms", []),
        context.get("danger_signs", []),
        f"{age_text} {age_unit}",
    )
    return {"role": "assistant", "payload": payload}


def _handle_chat_turn(store, prompt: str) -> None:
    prompt = prompt.strip()
    if not prompt:
        return

    if re.search(r"\b(start over|reset|new child|clear chat|start again)\b", prompt.lower()):
        _reset_chat()
        _append_chat("assistant", "No problem. Let's start again. How old is your child, and what symptoms are you noticing?")
        return

    _append_chat("user", prompt)
    context = st.session_state["chat_context"]
    age = _parse_age(prompt)
    if age:
        context["age_value"], context["age_unit"] = age
    context["symptoms"] = _dedupe(
        list(context.get("symptoms", [])) + _keywords_to_keys(prompt, CHAT_SYMPTOM_KEYWORDS)
    )
    context["danger_signs"] = _dedupe(
        list(context.get("danger_signs", [])) + _keywords_to_keys(prompt, CHAT_DANGER_KEYWORDS)
    )
    st.session_state["chat_context"] = context

    if context.get("danger_signs") and context.get("age_value") is None:
        _append_chat(
            "assistant",
            "This sounds like an emergency. Call your local emergency number or go to the nearest "
            "emergency department now. Do not wait. If you can, tell me your child's age, but do not delay care.",
        )
        return

    if context.get("age_value") is None or not (context.get("symptoms") or context.get("danger_signs")):
        _append_chat("assistant", _chat_missing_info_reply(context))
        return

    if store is None or not store.available:
        _append_chat(
            "assistant",
            "The guideline index is not loaded yet. Use the sidebar button to load it, then send your message again.",
        )
        return

    st.session_state["chat_messages"].append(_chat_run_guidance(store, context))


def render_chat_page(store) -> None:
    _ensure_chat_state()
    with st.container(key="chat_page"):
        with st.container(horizontal=True):
            if st.button(":material/arrow_back: Back to assessment", key="chat_back"):
                st.session_state["chat_open"] = False
                st.rerun()
            if st.button(":material/restart_alt: Start over", key="chat_reset"):
                _reset_chat()
                st.rerun()

        st.markdown(
            '<div class="bc-chat-hero">'
            '<div class="bc-kicker">BabyCare helper</div>'
            "<h1>Chat about your child's symptoms</h1>"
            '<p class="bc-muted">Tell me your child\'s age and what you are noticing in your own words. '
            "I will search the pediatric guidelines and share possible explanations, how urgent it seems, "
            "and what to do next. I cannot diagnose. If this is an emergency, call your local emergency number now.</p>"
            "</div>",
            unsafe_allow_html=True,
        )

        if store is None or not store.available:
            st.warning("The guideline index is not loaded yet. Use the sidebar button to load it first.")

        for message in st.session_state["chat_messages"]:
            with st.chat_message(message.get("role", "assistant")):
                payload = message.get("payload")
                if payload:
                    _render_chat_result(payload, show_header=False)
                else:
                    st.markdown(message.get("text", ""))

        if len(st.session_state["chat_messages"]) == 1:
            st.caption('Try: "My 18 month old has a fever and a cough." Or: "My 2 year old is not drinking."')

        st.caption("This chat supports, but does not replace, clinician assessment.")
        prompt = st.chat_input(
            "Describe your child's age and symptoms...",
            key="chat_input",
        )
        if prompt:
            _handle_chat_turn(store, prompt)
            st.rerun()


def render_assessment(store) -> None:
    st.markdown(
        '<div class="bc-hero">'
        '<div class="bc-kicker">BabyCare AI</div>'
        "<h1>Pediatric assistant ai</h1>"
        "</div>",
        unsafe_allow_html=True,
    )

    if store is None or not store.available:
        st.warning(
            "No local document index is loaded. Use 'Download / refresh and index documents' in the sidebar before running an assessment."
        )

    with st.form("assessment_form", clear_on_submit=False):
        _section(
            "Step 1",
            "Child details and measurements",
            "Enter the child and parent names for this session. Names are withheld from downloaded reports .",
        )
        c1, c2, c3 = st.columns([1.2, 1.2, 1.0])
        child_name = c1.text_input("Child name", placeholder="Child's name")
        parent_name = c2.text_input("Parent name", placeholder="Parent or guardian")
        dob_text = c3.text_input("Date of birth (optional)", placeholder="YYYY-MM-DD")

        c1, c2, c3, c4, c5 = st.columns(5)
        age_value_text = c1.text_input("Age value", placeholder="e.g. 3", help="Leave blank if using date of birth.")
        age_unit = c2.selectbox("Age unit", ["months", "days", "years"])
        sex = c3.selectbox("Sex", ["", "Female", "Male", "Other / unknown"])
        weight_text = c4.text_input("Weight (kg)", placeholder="e.g. 7.4")
        length_text = c5.text_input("Length or height (cm)", placeholder="e.g. 66")

        _section("Step 2", "Vital signs", "Leave a field blank if it was not measured. A blank value is never treated as normal.")
        c1, c2, c3 = st.columns(3)
        temperature_text = c1.text_input("Temperature (C)", placeholder="e.g. 38.2")
        respiratory_text = c2.text_input("Respiratory rate (/min)", placeholder="e.g. 44")
        heart_text = c3.text_input("Heart rate (/min)", placeholder="e.g. 130")

        _section("Step 3", "Presenting problem", "Select the reported symptoms and any danger signs observed or reported.")
        c1, c2 = st.columns(2)
        symptoms = c1.multiselect(
            "Symptoms",
            options=list(be.SYMPTOM_LABELS.keys()),
            format_func=lambda key: be.SYMPTOM_LABELS[key],
        )
        danger_signs = c2.multiselect(
            "Danger signs",
            options=list(be.DANGER_LABELS.keys()),
            format_func=lambda key: be.DANGER_LABELS[key],
        )

        st.caption("Names remain in this session and are withheld from downloaded reports.")
        submitted = st.form_submit_button("Run BabyCare assessment", type="primary", width="stretch")

    if not submitted:
        return

    patient = {
        "name": child_name.strip(),
        "parent_name": parent_name.strip(),
        "sex": sex,
        "weight_kg": _float_or_none(weight_text),
        "length_cm": _float_or_none(length_text),
        "vitals": {
            "temperature_c": _float_or_none(temperature_text),
            "respiratory_rate": _float_or_none(respiratory_text),
            "heart_rate": _float_or_none(heart_text),
        },
        "vitals_not_collected": ["spo2", "bp_systolic"],
        "symptoms": symptoms,
        "danger_signs": danger_signs,
    }
    dob = dob_text.strip()
    if dob:
        patient["dob"] = dob
    else:
        patient["age_value"] = age_value_text.strip()
        patient["age_unit"] = age_unit

    validation = be.validate_patient(patient)
    for error in validation["errors"]:
        st.error(error)
    for warning in validation["warnings"]:
        st.warning(warning)
    if validation["errors"]:
        st.stop()
    if store is None or not store.available:
        st.error("No document index is loaded. Use the sidebar button to download and index the guidelines first.")
        st.stop()

    try:
        with st.spinner("Running safety rules, retrieving guideline evidence, and verifying the selected condition..."):
            report = be.run_agents(patient, store, llm=be.LLMClient())
    except Exception as exc:
        st.error(f"Assessment failed: {exc}")
        st.stop()

    st.session_state["report"] = report
    st.session_state["patient"] = patient
    st.session_state["assessment_warnings"] = validation["warnings"]
    st.rerun()


def _urgency_class(level: str) -> str:
    return {"Emergency": "bc-emergency", "Urgent": "bc-urgent", "Routine": "bc-routine"}.get(level, "")


def _value(value: object, unit: str = "") -> str:
    if value is None or value == "":
        return "not recorded"
    return f"{value}{unit}"


def render_results(report, store) -> None:
    urgency = report.get("urgency", {})
    level = urgency.get("level", "not assessed")
    reasons = urgency.get("reasons", [])
    profile = report.get("profile", {})
    diseases = report.get("diseases", [])
    primary = diseases[0] if diseases else None

    st.markdown(
        '<div class="bc-hero">'
        '<div class="bc-kicker">BabyCare AI report</div>'
        "<h1>Clinical decision-support summary</h1>"
        '<p class="bc-muted">Safety rules, the selected condition, retrieved guideline evidence, and verification are shown separately. '
        "This is not a diagnosis and does not replace clinician assessment.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    reason_html = "<br>".join(_escape(reason) for reason in reasons[:8])
    if len(reasons) > 8:
        reason_html += "<br>Additional reasons are listed in the safety reasons section."
    st.markdown(
        f'<div class="bc-banner {_urgency_class(level)}">'
        f'<div class="bc-kicker">Urgency</div><strong>{_escape(level)}</strong>'
        f'<div>{reason_html or "No urgency reason was recorded."}</div>'
        "</div>",
        unsafe_allow_html=True,
    )

    for warning in st.session_state.get("assessment_warnings", []):
        st.warning(warning)

    with st.container(border=True):
        st.markdown("### Assessment summary")
        patient = st.session_state.get("patient", {})
        c1, c2 = st.columns(2)
        c1.markdown("**Child name**")
        c1.write(patient.get("name") or "not recorded")
        c2.markdown("**Parent name**")
        c2.write(patient.get("parent_name") or "not recorded")
        if primary:
            st.markdown(f"**Best-supported condition:** {primary.get('name', '')}")
            st.write(primary.get("explanation") or "Selected from the reported findings and retrieved evidence.")
            st.caption(f"Evidence status: {primary.get('evidence_status', '')}")
        else:
            st.write(report.get("summary", ""))
        st.caption(report.get("disclaimer", be.DISCLAIMER))
        st.caption(f"Generated {report.get('generated_at', '')}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Age", _value(profile.get("age_months"), " months"))
    c2.metric("Age band", profile.get("age_band", "not recorded"))
    c3.metric("Weight", _value(profile.get("weight_kg"), " kg"))
    c4.metric("Temperature", _value(profile.get("vitals", {}).get("temperature_c"), " C"))

    if primary and primary.get("serious"):
        st.markdown('<span class="bc-pill">Serious condition flagged</span>', unsafe_allow_html=True)

    if report.get("contradictions"):
        with st.container(border=True):
            st.markdown("### Contradictions or information gaps")
            for item in report["contradictions"]:
                st.warning(item)

    _section(
        "Step 4",
        "Best-supported condition",
        "One condition is selected from the reported symptoms and the available guideline evidence. It is not a confirmed diagnosis.",
    )
    if not primary:
        st.info("No condition met the evidence rules. This does not exclude serious illness.")
    for disease in diseases[:1]:
        with st.container(border=True):
            c1, c2 = st.columns([3.4, 1.6])
            c1.markdown(f"### {disease.get('name', '')}")
            status = disease.get("evidence_status", "")
            serious = "Serious condition" if disease.get("serious") else "Non-serious condition"
            c2.markdown(f'<span class="bc-pill">{_escape(status)}</span>', unsafe_allow_html=True)
            st.caption(serious)
            c1, c2 = st.columns(2)
            c1.markdown("**Why selected**")
            c1.write(", ".join(disease.get("why_considered", [])) or "Graph match")
            c1.markdown("**Risk factors**")
            c1.write(", ".join(disease.get("risk_factors", [])) or "none recorded")
            c2.markdown("**Information still needed**")
            c2.write(", ".join(disease.get("information_needed", [])) or "none listed")
            c2.markdown("**Possible complications**")
            c2.write(", ".join(disease.get("complications", [])) or "not listed")
            st.caption(disease.get("graph_note", be.GRAPH_NOTE))
            if disease.get("llm_note"):
                st.info(disease["llm_note"])
            if disease.get("evidence"):
                with st.expander("Evidence excerpts and sources"):
                    for passage in disease.get("evidence", [])[:4]:
                        st.markdown(
                            f"**{_escape(passage.get('organization', ''))}** | {_escape(passage.get('title', ''))} | page {_escape(passage.get('page', ''))}"
                        )
                        st.write(passage.get("text", ""))
                        if passage.get("url"):
                            st.markdown(f"[Open source]({passage.get('url')})")
            else:
                st.caption("No indexed passage was retrieved for this condition.")

    _section(
        "Step 5",
        "Investigation considerations",
        "These are discussion prompts for the clinician. They are not orders. Testing depends on the clinical setting and available resources.",
    )
    investigations = report.get("investigations", [])
    if primary:
        investigations = [
            item
            for item in investigations
            if primary.get("name") in item.get("helps_assess", [])
            or any(str(value).lower() == "any" for value in item.get("helps_assess", []))
        ]
    if investigations:
        rows = [
            {
                "Test": item.get("test", ""),
                "Why it may help": item.get("why", ""),
                "Helps assess": ", ".join(item.get("helps_assess", [])),
                "Age consideration": item.get("age_consideration", ""),
            }
            for item in investigations
        ]
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("No investigation suggestion was generated. The clinician decides all testing.")

    _section("Step 6", "Follow-up questions", "Answering these may improve the safety assessment. Answers stay in this session.")
    questions = report.get("followup_questions", [])
    if primary:
        primary_id = str(primary.get("id", ""))
        questions = [
            question
            for question in questions
            if not str(question.get("id", "")).startswith("info_")
            or str(question.get("id", "")).startswith(f"info_{primary_id}_")
        ]
    if questions:
        keys = {}
        with st.form("followup_form"):
            columns = st.columns(2)
            for index, question in enumerate(questions):
                key = f"fu_{index}_{question.get('id', index)}"
                keys[question.get("id", str(index))] = key
                with columns[index % 2]:
                    st.text_input(question.get("question", ""), key=key, help=question.get("reason", ""))
            updated = st.form_submit_button("Update assessment with these answers", type="primary", width="stretch")
        if updated:
            patient = st.session_state.get("patient")
            if not patient:
                st.error("The original assessment is not available in this session.")
            elif store is None or not store.available:
                st.error("The document index is not loaded.")
            else:
                answers = {question_id: st.session_state.get(key, "") for question_id, key in keys.items()}
                for key in list(st.session_state.keys()):
                    if key.startswith("fu_"):
                        del st.session_state[key]
                try:
                    with st.spinner("Updating the safety assessment and evidence review..."):
                        updated_patient = be.apply_followup_answers(patient, answers)
                        updated_report = be.run_agents(updated_patient, store, llm=be.LLMClient())
                except Exception as exc:
                    st.error(f"Update failed: {exc}")
                else:
                    st.session_state["patient"] = updated_patient
                    st.session_state["report"] = updated_report
                    st.rerun()
    else:
        st.info("No follow-up questions were generated.")

    _section("Step 7", "References", "References are drawn only from indexed documents. No reference or page number is invented.")
    references = primary.get("references", []) if primary else report.get("references", [])
    if references:
        for ref in references:
            label = f"{ref.get('organization', '')} | {ref.get('title', '')} | {ref.get('date', '')} | page {ref.get('page', '')}"
            if ref.get("url"):
                st.markdown(f"[{_escape(label)}]({ref.get('url')})")
            else:
                st.write(label)
    else:
        st.info("No indexed reference was retrieved.")

    if primary:
        primary_name = str(primary.get("name", "")).lower()
        other_names = [str(disease.get("name", "")).lower() for disease in diseases[1:]]
        verification_notes = [
            note
            for note in report.get("verification_notes", [])
            if primary_name in note.lower()
            and not any(other and other in note.lower() for other in other_names)
        ]
    else:
        verification_notes = []
    with st.expander("Verification notes"):
        for note in verification_notes or ["Automated verification completed. Clinician review is still required."]:
            st.write(note)

    with st.expander("Agent activity log"):
        for entry in report.get("agent_log", []):
            st.write(f"**{entry.get('agent', '')}**: {entry.get('detail', '')}")

    st.divider()
    c1, c2 = st.columns(2)
    markdown_report = be.report_to_markdown(report, primary_only=True)
    c1.download_button(
        "Download report (Markdown)",
        data=markdown_report,
        file_name=f"babycare_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
        mime="text/markdown",
        width="stretch",
    )
    if c2.button("Start a new assessment", width="stretch"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.caption(be.DISCLAIMER)


def main() -> None:
    if "chat_open" not in st.session_state:
        st.session_state["chat_open"] = False
    store = get_store()
    render_sidebar(store)
    if st.session_state["chat_open"]:
        render_chat_page(store)
        return
    render_chat_launcher()
    report = st.session_state.get("report")
    if report:
        render_results(report, store)
    else:
        render_assessment(store)


if __name__ == "__main__":
    main()
