import streamlit as st
import json
import os
import datetime
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Load .env for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Also pull from Streamlit Cloud secrets if running hosted
try:
    for _key in ["GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "CRI_RECIPIENT", "ANTHROPIC_API_KEY"]:
        if _key in st.secrets and not os.environ.get(_key):
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
APP_TITLE = "CRI Research Intake"
SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

FORM_SCHEMA = {
    "project_basics": {
        "section_label": "Project Basics",
        "fields": {
            "project_name": {
                "label": "Project Name",
                "description": "A short, descriptive name for this research project.",
                "priority": "critical",
            },
            "requestor": {
                "label": "Requestor",
                "description": "Who is submitting this request?",
                "priority": "critical",
            },
            "day_to_day_contact": {
                "label": "Day-to-Day Project Contact",
                "description": "Who should CRI work with on a daily basis?",
                "priority": "important",
            },
            "sponsor": {
                "label": "Sponsor",
                "description": "Who is the executive sponsor backing this work?",
                "priority": "important",
            },
            "stakeholders_scope": {
                "label": "Stakeholders for Input to Scope",
                "description": "Who should weigh in on what we research and how?",
                "priority": "important",
            },
            "stakeholders_report": {
                "label": "Additional Stakeholders for Report Out",
                "description": "Who else needs to see the results?",
                "priority": "nice_to_have",
            },
            "timing": {
                "label": "Timing",
                "description": "When do you need this? Any hard deadlines?",
                "priority": "critical",
            },
        },
    },
    "need_and_purpose": {
        "section_label": "Project Need and Purpose",
        "fields": {
            "business_context": {
                "label": "Business Context & Justification",
                "description": "Why is this work needed now? What business situation is driving this?",
                "priority": "critical",
            },
            "primary_business_questions": {
                "label": "Primary Business Question(s)",
                "description": "What specific business question are you trying to answer? What decisions will the results drive?",
                "priority": "critical",
            },
            "intended_decision_action": {
                "label": "Intended Decision/Action",
                "description": "What will you actually DO with the results?",
                "priority": "critical",
            },
            "inputs_to_decision": {
                "label": "Inputs to Decision",
                "description": "What specific inputs are you looking for from CRI? How will these feed the decision?",
                "priority": "critical",
            },
            "current_hypothesis": {
                "label": "Current Hypothesis",
                "description": "What do you currently believe the answer is? What assumptions are you making? What data supports those assumptions?",
                "priority": "critical",
            },
            "primary_objective": {
                "label": "Primary Objective",
                "description": "Explore, Validate, Track/Measure, or Prioritize?",
                "priority": "important",
            },
        },
    },
    "existing_knowledge": {
        "section_label": "Existing Knowledge",
        "fields": {
            "existing_information": {
                "label": "Existing Information & Other Inputs",
                "description": "What do we already know? What existing data, dashboards, or past research exists?",
                "priority": "important",
            },
            "gap_this_fills": {
                "label": "Gap This Project Fills",
                "description": "What unique contribution will this research provide that isn't available elsewhere?",
                "priority": "important",
            },
        },
    },
    "project_details": {
        "section_label": "Project Details",
        "fields": {
            "core_audience": {
                "label": "Core Audience",
                "description": "Who are the target consumers for this research? Why this audience?",
                "priority": "critical",
            },
            "key_subgroups": {
                "label": "Key Sub-groups",
                "description": "Any key sub-groups or comparisons needed?",
                "priority": "important",
            },
            "geography": {
                "label": "Geography",
                "description": "What geographies? CRI is primarily US-funded; other regions may need co-funding.",
                "priority": "important",
            },
            "output_requested": {
                "label": "Output Requested",
                "description": "Any specific deliverables expected? MVP?",
                "priority": "nice_to_have",
            },
        },
    },
    "project_impact": {
        "section_label": "Project Impact",
        "fields": {
            "scope_of_impact": {
                "label": "Scope of Impact",
                "description": "How big of an impact on Bose? Revenue, spend, reach?",
                "priority": "important",
            },
            "risk_of_not_doing": {
                "label": "Risk of Not Doing",
                "description": "What happens if we don't do this research?",
                "priority": "important",
            },
            "key_metrics": {
                "label": "Key Metrics",
                "description": "What business metrics/KPIs will this influence?",
                "priority": "important",
            },
            "what_success_looks_like": {
                "label": "What Success Looks Like",
                "description": "What's a realistic target for how this work will move the needle?",
                "priority": "nice_to_have",
            },
        },
    },
    "final_evaluation": {
        "section_label": "Final Evaluation",
        "fields": {
            "size_of_business_impact": {
                "label": "Size of Business Impact",
                "description": "High / Medium / Low",
                "priority": "important",
            },
            "confidence_level": {
                "label": "Confidence Level",
                "description": "High / Medium / Low — how much do we already know?",
                "priority": "important",
            },
            "type_of_decision": {
                "label": "Type of Decision",
                "description": "Irreversible / Moderate Flexibility / Easy to Pivot",
                "priority": "important",
            },
            "overall_risk_of_doing_nothing": {
                "label": "Overall Risk of Doing Nothing",
                "description": "High / Medium / Low",
                "priority": "important",
            },
        },
    },
}


def get_all_field_keys():
    keys = []
    for section in FORM_SCHEMA.values():
        keys.extend(section["fields"].keys())
    return keys


def get_field_info(field_key):
    for section in FORM_SCHEMA.values():
        if field_key in section["fields"]:
            return section["fields"][field_key]
    return None


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------
def build_system_prompt(extracted_fields: dict, coverage: dict):
    # Build a summary of what's been learned so far from the conversation
    conversation_summary = ""
    for section_key, section in FORM_SCHEMA.items():
        for field_key, field_info in section["fields"].items():
            value = extracted_fields.get(field_key)
            if value:
                conversation_summary += f"  - {field_info['label']}: {value}\n"

    system_prompt = f"""You are a principal-level consumer insights researcher at Bose's CRI (Consumer Research & Insights) team. You are having a real conversation with a business stakeholder who needs research.

## WHO YOU ARE
You are the researcher every stakeholder wishes they had: sharp, genuinely curious, warm, a real thought partner. You've run a thousand projects and you know the difference between a brief that produces great work and one that wastes everyone's time. You are NOT administering a form. You are having a conversation with a colleague.

## TONE IN CONVERSATION
Collegial and direct. Think: the smartest person in the room who doesn't need to prove it. Confident without being clinical. Dry wit when it fits. No filler affirmations ("Great point," "Absolutely"). No greetings or pleasantries. Just engage — pick up what they said and move it forward.

**CRITICAL RULE: In the conversation with the stakeholder, you are a neutral, curious probe — NOT an advisor injecting your own opinions or steering them toward a particular answer. Your job is to draw out THEIR thinking with the most incisive questions possible. Light personality is welcome. Opinions about their business decisions are not.**

**CRITICAL: You are having a free-form conversation, NOT collecting form fields. There is no checklist. There is no form. Your job is to deeply understand what this person needs through genuine dialogue — the way a seasoned researcher would over coffee. Ask the ONE most valuable question available at any moment. Follow threads that matter. Let the conversation breathe.**

## HOW YOU CONDUCT THIS CONVERSATION
Your job is to deeply understand what this person actually needs. Not to fill boxes — to understand. Here's how:

- **Listen for what's NOT being said** as much as what is. The real problem is often one layer beneath what they lead with.
- **Follow the interesting thread**, not the next checkbox. If they mention something rich, go there. Don't abandon a substantive thread to collect a logistics field.
- **Ask one question at a time.** Never list multiple questions. Each question should be the sharpest, most useful one available given what you know.
- **Ask synthesizing questions**, not data-collection questions. Instead of "what's your timeline?" ask something that surfaces the timeline AND the stakes AND the urgency in one move.
- **Reflect back what you're hearing** to help them clarify their own thinking. A great intake conversation leaves the stakeholder understanding their own project better than when they walked in.
- **Push on assumptions** without telegraphing pushback. Just ask the question that surfaces the gap.
- **Never say:** "let me push on this," "I want to make sure I understand," "can you clarify," "that's vague," or any meta-commentary. Just engage directly.
- **No opinion injection toward the stakeholder.** You can be warm, a little funny, totally engaged — but you don't editorialize about their strategy. Save that for the Researcher Notes.

## WHAT YOU NEED TO UNDERSTAND (your internal compass, not a script)
Through natural conversation, come to understand:

1. **The real problem** — What's the business situation? What decision hangs on this? Why now?
2. **What they'll do with the answer** — If you hand them perfect research, what happens next? What changes?
3. **Their current thinking** — What do they already believe? How confident are they? What would change their mind?
4. **Who we're studying** — What consumers, what geography, are there meaningful sub-groups?
5. **What already exists** — What data, past research, or intuition do they have? What gap does this uniquely fill?
6. **The stakes** — How big is this for the business? What's the risk of not doing it?
7. **Logistics** — Who's involved, who's the sponsor, when do they need it? (Let these come out naturally — don't front-load admin.)

## PACING
- Start with the substance (the problem, the decision, the why). Admin comes later naturally.
- Go deep before going broad. Understand the core before asking about audience, geography, logistics.
- Use as few questions as possible to get as much as possible. Quality over quantity.
- When you feel you have a rich enough picture, offer to wrap up: *"I think I have what I need. Want me to write this up?"*

## WHAT YOU'VE LEARNED SO FAR
{conversation_summary if conversation_summary else "(Conversation just started — nothing captured yet.)"}

## ALREADY CAPTURED UPFRONT (do NOT ask about any of these)
The following were provided before the conversation started. Treat them as known. Reference naturally if relevant, never ask again:
- Requestor / name: {extracted_fields.get("requestor") or "not provided"}
- Project name: {extracted_fields.get("project_name") or "not provided"}
- Sponsor: {extracted_fields.get("sponsor") or "not provided"}
- Stakeholders for scoping: {extracted_fields.get("stakeholders_scope") or "not provided"}
- Stakeholders for report-out: {extracted_fields.get("stakeholders_report") or "not provided"}
- Timing: {extracted_fields.get("timing") or "not provided"}
- Self-assessed business impact: {extracted_fields.get("size_of_business_impact") or "not provided"}
- Self-assessed existing knowledge: {extracted_fields.get("confidence_level") or "not provided"}
- Decision reversibility: {extracted_fields.get("type_of_decision") or "not provided"}
- Self-assessed risk of not doing: {extracted_fields.get("overall_risk_of_doing_nothing") or "not provided"}

## GENERATING THE OUTPUT
When the stakeholder confirms they're ready to wrap up, generate a research brief using EXACTLY this format. The brief is written FOR the CRI researcher team — NOT for the stakeholder. Write it like you just got off a call and are briefing your team in Slack, except it's a formal doc. You have a voice here. Use it.

===BRIEF_OUTPUT_START===
**Project:** [name and requestor]
**Deadline:** [timing]
**Sponsor:** [if known]

**The Situation**
[2-3 sentences: what's going on in the business, why this research is needed now. Be specific — not "they want to grow" but what's actually happening and why it matters now.]

**The Core Question**
[The actual research question in plain language — not corporate-speak. What do we genuinely need to understand to make progress?]

**What They'll Do With It**
[What decision or action this research will feed. Be concrete: what gets built, killed, funded, changed, or presented to whom.]

**Their Current Hypothesis**
[What they believe going in, what data or gut feeling backs it, how open they seem to being wrong. Be honest about the confidence level.]

**Who We're Studying**
[Target consumers, geography, any key sub-groups that matter for the analysis.]

**What We Already Know**
[Existing data, past research, context that's in the room — and what unique gap this project fills that we don't already have.]

**The Stakes**
[Business impact, risk of not doing it, what metrics or decisions this touches. Give a real read on how important this actually is.

Also incorporate the stakeholder's own self-assessment from the intake form:
- They rated business impact as: {extracted_fields.get("size_of_business_impact") or "not provided"}
- Their existing knowledge level: {extracted_fields.get("confidence_level") or "not provided"}
- Decision reversibility: {extracted_fields.get("type_of_decision") or "not provided"}
- Risk of not doing it: {extracted_fields.get("overall_risk_of_doing_nothing") or "not provided"}

Weave these in naturally — don't just list them. If any feel inconsistent with what came out in conversation, flag that in Researcher Notes.]

**Recommended Methodology**
[Your professional recommendation on approach. Be direct: qual, quant, or mixed — and why this project calls for that. Consider: Is this an exploration (qual makes sense), a validation (survey/quant), a decision with real money on it (mixed for confidence), or a tracking need (quant longitudinal)? Give a brief rationale — 2-3 sentences. If there's a strong reason to push back on what they asked for, say so here.]

**Researcher Notes**
[This is your insider briefing to the team. Write it like you're debriefing a colleague after getting off the call — professional but casual, first-person voice, allowed to have a take.

Cover:
- What's the real subtext here? What's the actual pressure or political situation driving this ask?
- What's the stakeholder NOT saying that the team should know going into scoping?
- Where is their thinking solid vs. where are there gaps or assumptions that need pressure-testing?
- Any red flags: scope creep risk, hypothesis that's really a conclusion, timeline that doesn't match the ambition, stakeholder who seems to want validation not insight?
- What's the one thing we absolutely must nail in scoping to make this project successful?
- What follow-up questions should the researcher ask in the scoping call?

Don't be timid here. If the ask is fuzzy, say so. If their hypothesis feels baked-in, flag it. If the timeline is unrealistic for what they're describing, note it. This is the brief the researcher reads before picking up the phone — make it useful.]
===BRIEF_OUTPUT_END===

===EMAIL_SUMMARY_START===
[A short, human summary — 3-4 sentences max — for the intake notification email. Just the essence: who, what, why it matters, when needed. No corporate boilerplate.]
===EMAIL_SUMMARY_END===

## EXTRACTION (system use only — never show this to user)
After EVERY response (including conversational ones), silently append this JSON block. Extract only what the user has explicitly stated — do not infer or fill from your own questions.

===EXTRACTED_START===
{{
  "project_name": "short name if mentioned or null",
  "requestor": "person's name if mentioned or null",
  "timing": "deadline if mentioned or null",
  "business_context": "the core business situation in 1-2 sentences or null",
  "primary_business_questions": "the main research question in plain language or null",
  "intended_decision_action": "what they'll do with results or null",
  "core_audience": "who we'd study or null"
}}
===EXTRACTED_END===
"""
    return system_prompt


# ---------------------------------------------------------------------------
# LLM Integration
# ---------------------------------------------------------------------------
def call_llm(messages, system_prompt, api_key=None):
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
            )
            return response.content[0].text
        except Exception as e:
            return f"**API Error:** {str(e)}\n\nPlease check your API key and try again.\n\n===EXTRACTED_START===\n{{}}\n===EXTRACTED_END==="
    else:
        return run_demo_mode(messages)


def run_demo_mode(messages):
    turn = len([m for m in messages if m["role"] == "user"])
    null_fields = json.dumps({key: None for key in get_all_field_keys()})

    demo_responses = [
        f"""What's going on — tell me about the project.

===EXTRACTED_START===
{null_fields}
===EXTRACTED_END===""",

        f"""Got it. And what's the actual decision this needs to feed? Like, if we came back with the perfect answer, what would you do with it?

===EXTRACTED_START===
{json.dumps({**{key: None for key in get_all_field_keys()}, "business_context": "Captured from user response"})}
===EXTRACTED_END===""",

        f"""What's your current read on it — do you have a hypothesis going in?

===EXTRACTED_START===
{json.dumps({**{key: None for key in get_all_field_keys()}, "business_context": "Captured", "primary_business_questions": "Captured", "intended_decision_action": "Captured"})}
===EXTRACTED_END===""",

        f"""Who are we actually talking to for this — what's the consumer target?

===EXTRACTED_START===
{json.dumps({**{key: None for key in get_all_field_keys()}, "business_context": "Captured", "primary_business_questions": "Captured", "intended_decision_action": "Captured", "current_hypothesis": "Captured", "existing_information": "Captured"})}
===EXTRACTED_END===""",

        f"""How big is this for the business — are we talking a major bet or more of a supporting input?

===EXTRACTED_START===
{json.dumps({**{key: None for key in get_all_field_keys()}, "business_context": "Captured", "primary_business_questions": "Captured", "intended_decision_action": "Captured", "current_hypothesis": "Captured", "existing_information": "Captured", "core_audience": "Captured", "geography": "Captured", "key_subgroups": "Captured"})}
===EXTRACTED_END===""",

        f"""I think I have what I need — want me to pull this together into the intake form?

*(In live mode with an API key, I'd generate the completed form and email summary here.)*

===EXTRACTED_START===
{json.dumps({key: "Captured" for key in get_all_field_keys()})}
===EXTRACTED_END===""",
    ]

    if turn <= len(demo_responses):
        return demo_responses[turn - 1]
    else:
        return f"""Add your Anthropic API key in the sidebar to enable the full experience, including generating the completed intake form.

===EXTRACTED_START===
{{}}
===EXTRACTED_END==="""


# ---------------------------------------------------------------------------
# Extraction & Coverage
# ---------------------------------------------------------------------------
def extract_fields_from_response(response_text, current_fields):
    updated = dict(current_fields)
    try:
        start_marker = "===EXTRACTED_START==="
        end_marker = "===EXTRACTED_END==="
        if start_marker in response_text and end_marker in response_text:
            start = response_text.index(start_marker) + len(start_marker)
            end = response_text.index(end_marker)
            json_str = response_text[start:end].strip()
            extracted = json.loads(json_str)
            for key, value in extracted.items():
                if value is not None and value != "null":
                    updated[key] = value
    except (json.JSONDecodeError, ValueError):
        pass
    return updated


def extract_form_output(response_text):
    form_output = None
    email_output = None
    # Support new BRIEF_OUTPUT marker (preferred) and legacy FORM_OUTPUT marker
    for start_marker, end_marker in [
        ("===BRIEF_OUTPUT_START===", "===BRIEF_OUTPUT_END==="),
        ("===FORM_OUTPUT_START===", "===FORM_OUTPUT_END==="),
    ]:
        try:
            if start_marker in response_text:
                start = response_text.index(start_marker) + len(start_marker)
                end = response_text.index(end_marker)
                form_output = response_text[start:end].strip()
                break
        except ValueError:
            pass
    try:
        if "===EMAIL_SUMMARY_START===" in response_text:
            start = response_text.index("===EMAIL_SUMMARY_START===") + len("===EMAIL_SUMMARY_START===")
            end = response_text.index("===EMAIL_SUMMARY_END===")
            email_output = response_text[start:end].strip()
    except ValueError:
        pass
    return form_output, email_output


def build_transcript_appendix(messages, extracted_fields):
    """Build a raw transcript block to append to the research brief for CRI researchers."""
    lines = []
    lines.append("\n\n---\n\n## Appendix: Raw Conversation Transcript\n")
    lines.append("*For CRI researcher reference — unedited stakeholder inputs from the intake conversation.*\n")

    # Pre-form structured inputs
    pre_form_fields = [
        ("Requestor", extracted_fields.get("requestor")),
        ("Project Name", extracted_fields.get("project_name")),
        ("Sponsor", extracted_fields.get("sponsor")),
        ("Stakeholders for Scoping", extracted_fields.get("stakeholders_scope")),
        ("Stakeholders for Report-Out", extracted_fields.get("stakeholders_report")),
        ("Timing", extracted_fields.get("timing")),
        ("Self-assessed Business Impact", extracted_fields.get("size_of_business_impact")),
        ("Self-assessed Existing Knowledge", extracted_fields.get("confidence_level")),
        ("Decision Reversibility", extracted_fields.get("type_of_decision")),
        ("Self-assessed Risk of Not Doing", extracted_fields.get("overall_risk_of_doing_nothing")),
    ]
    pre_form_lines = [(label, val) for label, val in pre_form_fields if val and val != "Not sure"]
    if pre_form_lines:
        lines.append("\n### Pre-conversation Form Inputs\n")
        for label, val in pre_form_lines:
            lines.append(f"**{label}:** {val}  ")

    # Conversation messages
    chat_msgs = [m for m in messages if m["role"] in ("user", "assistant")]
    if chat_msgs:
        lines.append("\n\n### Conversation\n")
        for msg in chat_msgs:
            display = msg.get("display_content") or msg.get("content", "")
            display = clean_response_for_display(display).strip()
            if not display:
                continue
            speaker = "**Stakeholder:**" if msg["role"] == "user" else "**CRI:**"
            lines.append(f"{speaker} {display}\n")

    return "\n".join(lines)


def clean_response_for_display(response_text):
    display = response_text
    for marker_pair in [
        ("===EXTRACTED_START===", "===EXTRACTED_END==="),
        ("===BRIEF_OUTPUT_START===", "===BRIEF_OUTPUT_END==="),
        ("===FORM_OUTPUT_START===", "===FORM_OUTPUT_END==="),
        ("===EMAIL_SUMMARY_START===", "===EMAIL_SUMMARY_END==="),
    ]:
        start_marker, end_marker = marker_pair
        while start_marker in display and end_marker in display:
            start = display.index(start_marker)
            end = display.index(end_marker) + len(end_marker)
            display = display[:start] + display[end:]
    return display.strip()


def compute_coverage(extracted_fields):
    total = covered = critical_total = critical_covered = important_total = important_covered = 0
    for section in FORM_SCHEMA.values():
        for field_key, field_info in section["fields"].items():
            total += 1
            has_value = bool(extracted_fields.get(field_key))
            if has_value:
                covered += 1
            if field_info["priority"] == "critical":
                critical_total += 1
                if has_value:
                    critical_covered += 1
            elif field_info["priority"] == "important":
                important_total += 1
                if has_value:
                    important_covered += 1
    return {
        "total": total,
        "covered": covered,
        "pct": int((covered / total) * 100) if total > 0 else 0,
        "critical_total": critical_total,
        "critical_covered": critical_covered,
        "important_total": important_total,
        "important_covered": important_covered,
    }


# ---------------------------------------------------------------------------
# Session Persistence
# ---------------------------------------------------------------------------
def save_session(session_id, messages, extracted_fields, form_output, email_output):
    session_data = {
        "session_id": session_id,
        "timestamp": datetime.datetime.now().isoformat(),
        "messages": messages,
        "extracted_fields": extracted_fields,
        "form_output": form_output,
        "email_output": email_output,
        "coverage": compute_coverage(extracted_fields),
    }
    filepath = SESSIONS_DIR / f"{session_id}.json"
    with open(filepath, "w") as f:
        json.dump(session_data, f, indent=2)


def load_session(session_id):
    filepath = SESSIONS_DIR / f"{session_id}.json"
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return None


def list_sessions():
    sessions = []
    for filepath in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
        try:
            with open(filepath) as f:
                data = json.load(f)
                sessions.append({
                    "id": data.get("session_id", filepath.stem),
                    "timestamp": data.get("timestamp", "Unknown"),
                    "project_name": data.get("extracted_fields", {}).get("project_name") or "Untitled",
                    "coverage": data.get("coverage", {}).get("pct", 0),
                })
        except (json.JSONDecodeError, KeyError):
            pass
    return sessions


# ---------------------------------------------------------------------------
# Bose Brand CSS
# ---------------------------------------------------------------------------
BOSE_CSS = """
<style>
/* ── Google Fonts fallback (Bose uses proprietary fonts; Inter is closest public match) ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&display=swap');

/* ── Root tokens ── */
:root {
    --bose-black:      #131317;
    --bose-white:      #FFFFFF;
    --bose-warm-bg:    #F8F1E7;
    --bose-light-bg:   #F1EFEE;
    --bose-mid-gray:   #3E474A;
    --bose-soft-gray:  #B4BEC7;
    --bose-divider:    #CFC8C5;
    --bose-accent:     #00A1E0;
    --bose-text:       #131317;
}

/* ── Global resets ── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    color: var(--bose-text) !important;
}

/* ── App background ── */
.stApp {
    background-color: var(--bose-white) !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: var(--bose-black) !important;
    border-right: none !important;
}
[data-testid="stSidebar"] * {
    color: var(--bose-white) !important;
}
[data-testid="stSidebar"] .stTextInput input {
    background-color: #1e1e24 !important;
    border: 1px solid #3E474A !important;
    border-radius: 2px !important;
    color: var(--bose-white) !important;
    font-size: 13px !important;
}
[data-testid="stSidebar"] .stProgress > div > div {
    background-color: var(--bose-accent) !important;
}
[data-testid="stSidebar"] .stProgress {
    background-color: #2a2a30 !important;
}
[data-testid="stSidebar"] hr {
    border-color: #2a2a30 !important;
}
[data-testid="stSidebar"] .stButton > button {
    background-color: transparent !important;
    border: 1px solid #3E474A !important;
    border-radius: 2px !important;
    color: var(--bose-white) !important;
    font-size: 12px !important;
    font-weight: 400 !important;
    text-align: left !important;
    width: 100% !important;
    padding: 6px 10px !important;
    letter-spacing: 0.3px !important;
    transition: border-color 0.2s, background-color 0.2s !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    border-color: var(--bose-accent) !important;
    background-color: #1e1e24 !important;
}
[data-testid="stSidebar"] .stAlert {
    background-color: #1e1e24 !important;
    border: 1px solid #3E474A !important;
    border-radius: 2px !important;
    font-size: 12px !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    font-weight: 700 !important;
    letter-spacing: -0.3px !important;
}

/* ── Main header ── */
.main-header {
    border-bottom: 1px solid var(--bose-divider);
    padding-bottom: 20px;
    margin-bottom: 32px;
}
.main-header .brand-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--bose-soft-gray);
    margin-bottom: 4px;
}
.main-header h1 {
    font-size: 28px !important;
    font-weight: 900 !important;
    letter-spacing: -0.5px !important;
    color: var(--bose-black) !important;
    margin: 0 !important;
    line-height: 1.1 !important;
}
.main-header .subtitle {
    font-size: 14px;
    color: var(--bose-mid-gray);
    margin-top: 6px;
    font-weight: 400;
}

/* ── Custom chat messages (rendered via st.markdown, not st.chat_message) ── */
.bose-msg {
    padding: 20px 0;
    border-bottom: 1px solid #F1EFEE;
}
.bose-msg-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--bose-soft-gray);
    margin-bottom: 8px;
    font-family: 'Inter', sans-serif;
}
.bose-msg-user {
    background-color: var(--bose-light-bg);
    border-radius: 2px;
    padding: 16px 20px;
    margin: 0 -4px;
}
.bose-msg-body {
    font-size: 15px;
    line-height: 1.7;
    color: var(--bose-text);
    font-family: 'Inter', sans-serif;
}
.bose-msg-body p { margin: 0 0 10px; }
.bose-msg-body p:last-child { margin-bottom: 0; }
.bose-msg-body strong { font-weight: 600; }
.bose-msg-body em { font-style: italic; }

/* ── Hide default Streamlit chat widgets (used only for input/spinner) ── */
[data-testid="stChatMessage"] {
    display: none !important;
}

/* ── Chat input ── */
[data-testid="stChatInput"] {
    border-top: 1px solid var(--bose-divider) !important;
    padding-top: 12px !important;
    background: var(--bose-white) !important;
}
[data-testid="stChatInput"] textarea {
    background-color: var(--bose-light-bg) !important;
    border: 1px solid var(--bose-divider) !important;
    border-radius: 2px !important;
    font-size: 15px !important;
    color: var(--bose-text) !important;
    font-family: 'Inter', sans-serif !important;
    padding: 12px 16px !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: var(--bose-black) !important;
    box-shadow: none !important;
    outline: none !important;
}
[data-testid="stChatInput"] button {
    background-color: var(--bose-black) !important;
    border-radius: 2px !important;
    border: none !important;
}
[data-testid="stChatInput"] button:hover {
    background-color: var(--bose-mid-gray) !important;
}

/* ── Spinner ── */
.stSpinner > div {
    border-top-color: var(--bose-black) !important;
}

/* ── Form output panels ── */
.output-panel {
    background-color: var(--bose-light-bg);
    border: 1px solid var(--bose-divider);
    border-radius: 2px;
    padding: 24px;
    margin-top: 8px;
}
.output-panel h3 {
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    color: var(--bose-soft-gray) !important;
    margin-bottom: 16px !important;
}

/* ── Download buttons ── */
[data-testid="stDownloadButton"] button {
    background-color: var(--bose-black) !important;
    color: var(--bose-white) !important;
    border: none !important;
    border-radius: 2px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    letter-spacing: 0.5px !important;
    padding: 10px 20px !important;
    transition: background-color 0.2s !important;
}
[data-testid="stDownloadButton"] button:hover {
    background-color: var(--bose-mid-gray) !important;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background-color: #1e1e24 !important;
    border-radius: 2px !important;
    padding: 10px 12px !important;
}
[data-testid="stMetric"] label {
    font-size: 10px !important;
    letter-spacing: 1.5px !important;
    text-transform: uppercase !important;
    color: var(--bose-soft-gray) !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 20px !important;
    font-weight: 700 !important;
    color: var(--bose-white) !important;
}

/* ── Expander ── */
[data-testid="stSidebar"] .streamlit-expanderHeader {
    font-size: 12px !important;
    font-weight: 500 !important;
    color: var(--bose-soft-gray) !important;
    letter-spacing: 0.3px !important;
}

/* ── Divider ── */
hr {
    border-color: var(--bose-divider) !important;
    margin: 24px 0 !important;
}

/* ── Pre-chat intake form ── */
[data-testid="stForm"] {
    background-color: var(--bose-light-bg) !important;
    border: 1px solid var(--bose-divider) !important;
    border-radius: 4px !important;
    padding: 28px 28px 20px !important;
    max-width: 700px !important;
    margin: 0 auto !important;
}
[data-testid="stForm"] label {
    font-size: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 0.5px !important;
    color: var(--bose-mid-gray) !important;
    text-transform: uppercase !important;
}
[data-testid="stForm"] input[type="text"] {
    border: 1px solid var(--bose-divider) !important;
    border-radius: 2px !important;
    font-size: 14px !important;
    background-color: var(--bose-white) !important;
}
[data-testid="stForm"] input[type="text"]:focus {
    border-color: var(--bose-black) !important;
    box-shadow: none !important;
}
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button {
    background-color: var(--bose-black) !important;
    color: var(--bose-white) !important;
    border: none !important;
    border-radius: 2px !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    letter-spacing: 0.5px !important;
    padding: 12px 24px !important;
    margin-top: 8px !important;
    width: 100% !important;
    transition: background-color 0.2s !important;
}
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button:hover {
    background-color: var(--bose-mid-gray) !important;
}

/* ── Radio buttons in form ── */
[data-testid="stForm"] [data-testid="stRadio"] label {
    font-size: 13px !important;
    font-weight: 400 !important;
    letter-spacing: 0 !important;
    text-transform: none !important;
    color: var(--bose-text) !important;
}
[data-testid="stForm"] [data-testid="stRadio"] > label {
    font-size: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 0.5px !important;
    text-transform: uppercase !important;
    color: var(--bose-mid-gray) !important;
}

/* ── Hide Streamlit branding ── */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--bose-divider); border-radius: 2px; }
</style>
"""


# ---------------------------------------------------------------------------
# Email Sender
# ---------------------------------------------------------------------------
def send_intake_email(form_text: str, email_summary: str, project_name: str, session_id: str):
    """
    Send the completed intake form to CRI via Gmail SMTP.
    Credentials come from .env or Streamlit secrets.
    Returns (success: bool, message: str).
    """
    gmail_address  = os.environ.get("GMAIL_ADDRESS", "").strip()
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    recipient      = os.environ.get("CRI_RECIPIENT", "erich_wiernasz@bose.com").strip()

    if not gmail_address or not gmail_password:
        return False, "Email credentials not configured. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to your .env file."

    # Build the email
    subject = f"Research Request: {project_name or 'New Request'} [{session_id}]"

    # Convert markdown brief to HTML for email
    try:
        import markdown as md_lib
        brief_html_content = md_lib.markdown(form_text, extensions=["extra"])
    except Exception:
        brief_html_content = f"<pre style='white-space:pre-wrap;'>{form_text}</pre>"

    html_body = f"""
<html><body style="font-family: Arial, sans-serif; color: #131317; max-width: 680px; margin: 0 auto;">

<div style="border-bottom: 2px solid #131317; padding-bottom: 12px; margin-bottom: 24px;">
  <div style="font-size: 11px; letter-spacing: 2px; text-transform: uppercase; color: #B4BEC7; margin-bottom: 4px;">
    Bose · Consumer Research &amp; Insights
  </div>
  <div style="font-size: 22px; font-weight: 900;">New Research Request</div>
</div>

{f'<div style="background: #F1EFEE; padding: 16px 20px; margin-bottom: 28px; border-radius: 2px; font-size: 14px; line-height: 1.6; color: #3E474A;">{email_summary}</div>' if email_summary else ''}

<div style="font-size: 14px; line-height: 1.8;">
{brief_html_content}
</div>

<div style="margin-top: 32px; padding-top: 16px; border-top: 1px solid #CFC8C5; font-size: 11px; color: #B4BEC7;">
  Submitted via CRI Research Intake · Session ID: {session_id}
</div>
</body></html>
"""

    # Plain text fallback
    plain_body = f"CRI Research Request: {project_name}\n\n{email_summary}\n\n---\n\n{form_text}\n\nSession ID: {session_id}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"CRI Intake Assistant <{gmail_address}>"
    msg["To"]      = recipient
    msg["Reply-To"] = gmail_address

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, recipient, msg.as_string())
        return True, "Intake form sent to CRI successfully."
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed. Check your Gmail address and App Password in the .env file."
    except Exception as e:
        return False, f"Could not send: {str(e)}"


# ---------------------------------------------------------------------------
# Message Renderer — fully custom, no Streamlit avatars
# ---------------------------------------------------------------------------
def render_message(role: str, content: str):
    """Render a chat message using our own HTML — no emoji avatars, clean Bose style."""
    import markdown as md_lib
    try:
        body_html = md_lib.markdown(content, extensions=["extra"])
    except Exception:
        # Fallback: basic paragraph wrapping if markdown lib isn't available
        body_html = "".join(f"<p>{line}</p>" for line in content.split("\n") if line.strip())

    if role == "user":
        st.markdown(
            f"""<div class="bose-msg bose-msg-user">
                <div class="bose-msg-label">You</div>
                <div class="bose-msg-body">{body_html}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""<div class="bose-msg">
                <div class="bose-msg-label">CRI</div>
                <div class="bose-msg-body">{body_html}</div>
            </div>""",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title="CRI Research Intake · Bose",
        page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' fill='%23131317'/><text y='.9em' font-size='80' x='10'>🎧</text></svg>",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Inject Bose CSS
    st.markdown(BOSE_CSS, unsafe_allow_html=True)

    # ── Sidebar ──
    with st.sidebar:
        st.markdown(
            "<div style='font-size:11px;font-weight:600;letter-spacing:2px;text-transform:uppercase;"
            "color:#B4BEC7;margin-bottom:16px;padding-top:8px;'>BOSE · CRI</div>",
            unsafe_allow_html=True,
        )

        # Use key from secrets/env if available — sidebar input is optional override
        _env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        api_key_input = st.text_input(
            "Anthropic API Key",
            type="password",
            help="Pre-configured. You can override here if needed.",
            placeholder="Using saved key" if _env_key else "sk-ant-...",
        )
        api_key = api_key_input or _env_key

        if api_key:
            st.markdown(
                "<div style='font-size:12px;color:#00A1E0;margin-top:-8px;'>● Live mode</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='font-size:12px;color:#B4BEC7;margin-top:-8px;'>○ Demo mode</div>",
                unsafe_allow_html=True,
            )

        st.divider()

        st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)
        if st.button("+ New Session"):
            for key in ["messages", "extracted_fields", "session_id", "form_output", "email_output", "email_sent", "email_status", "intake_submitted"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    # ── Init session state ──
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "extracted_fields" not in st.session_state:
        st.session_state.extracted_fields = {key: None for key in get_all_field_keys()}
    if "session_id" not in st.session_state:
        st.session_state.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if "form_output" not in st.session_state:
        st.session_state.form_output = None
    if "email_output" not in st.session_state:
        st.session_state.email_output = None
    if "email_sent" not in st.session_state:
        st.session_state.email_sent = False
    if "email_status" not in st.session_state:
        st.session_state.email_status = None
    if "intake_submitted" not in st.session_state:
        st.session_state.intake_submitted = False

    # ── Main header ──
    st.markdown(
        """
        <div class="main-header">
            <div class="brand-label">Bose · Consumer Research & Insights</div>
            <h1>Research Intake</h1>
            <div class="subtitle">Tell me what's going on. We'll figure out the brief together.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Pre-chat intake form ──
    if not st.session_state.intake_submitted:
        st.markdown(
            """
            <div style='max-width:600px;margin:0 auto 8px auto;'>
                <div style='font-size:13px;color:#3E474A;line-height:1.6;margin-bottom:28px;'>
                    Before we dig in, a few quick details so CRI has the basics on record.
                    The conversation will handle everything else.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("intake_pre_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                fi_name = st.text_input(
                    "Your Name *",
                    placeholder="e.g. Jamie Chen",
                )
                fi_project = st.text_input(
                    "Project Name",
                    placeholder="e.g. Q3 Headphone Positioning",
                    help="A working title is fine — we can refine it.",
                )
                fi_sponsor = st.text_input(
                    "Executive Sponsor",
                    placeholder="e.g. Sarah Lee, VP Marketing",
                    help="Who's backing this work at the leadership level?",
                )
                fi_stakeholders_scope = st.text_input(
                    "Stakeholders for Scoping",
                    placeholder="e.g. Product, Marketing, Sales",
                    help="Who should weigh in on what we research and how?",
                )
                fi_stakeholders_report = st.text_input(
                    "Stakeholders for Report-Out",
                    placeholder="e.g. CMO, Brand team",
                    help="Who needs to see the results?",
                )
                # Timing: quick radio + optional freetext
                timing_choice = st.radio(
                    "When do you need this?",
                    options=["Within 4 weeks", "1–2 months", "2–3 months", "3+ months", "Flexible / TBD"],
                    horizontal=False,
                )
                fi_timing_other = st.text_input(
                    "Hard deadline or context (optional)",
                    placeholder="e.g. Must inform Q4 planning by Oct 1",
                )

            with col_b:
                st.markdown(
                    "<div style='font-size:12px;font-weight:600;letter-spacing:0.5px;color:#3E474A;"
                    "text-transform:uppercase;margin-bottom:4px;'>Quick self-assessment</div>"
                    "<div style='font-size:12px;color:#7F8891;margin-bottom:16px;line-height:1.5;'>"
                    "Best guess is fine — these help CRI prioritize. Not sure? Pick the closest option.</div>",
                    unsafe_allow_html=True,
                )
                fi_impact = st.select_slider(
                    "Business impact if we get this right",
                    options=[
                        "Not sure",
                        "Small — supports a minor decision",
                        "Medium — meaningful but contained",
                        "Large — shapes a major bet",
                        "Transformational — company-level",
                    ],
                    value="Not sure",
                    help="How much does the outcome of this research matter to the business?",
                )
                fi_confidence = st.select_slider(
                    "How much do we already know?",
                    options=[
                        "Not sure",
                        "Starting from scratch",
                        "Some signals, lots of gaps",
                        "Decent baseline, need validation",
                        "Strong view, want to confirm",
                    ],
                    value="Not sure",
                    help="How much existing data or intuition does the team have on this topic?",
                )
                fi_decision_type = st.selectbox(
                    "How reversible is the decision this feeds?",
                    options=[
                        "Not sure",
                        "Easy to pivot — low cost to change course",
                        "Moderate — reversal is possible but costly",
                        "Hard to reverse — significant commitment",
                        "Irreversible — one-way door",
                    ],
                    help="If the research points somewhere unexpected, how hard is it to change direction?",
                )
                fi_risk = st.select_slider(
                    "Risk of not doing this research",
                    options=[
                        "Not sure",
                        "Low — we'll figure it out either way",
                        "Medium — some blind spots remain",
                        "High — real chance of a costly mistake",
                        "Critical — flying blind on a major call",
                    ],
                    value="Not sure",
                    help="What's the downside of moving forward without research?",
                )

            submitted = st.form_submit_button("Start the conversation →", type="primary", use_container_width=True)

        if submitted:
            if not fi_name.strip():
                st.error("Please enter your name so we know who we're talking to.")
            else:
                timing_val = timing_choice
                if fi_timing_other.strip():
                    timing_val = f"{timing_choice} — {fi_timing_other.strip()}"

                # Seed extracted fields with the pre-form data
                ef = st.session_state.extracted_fields
                ef["requestor"] = fi_name.strip()
                if fi_project.strip():
                    ef["project_name"] = fi_project.strip()
                if fi_sponsor.strip():
                    ef["sponsor"] = fi_sponsor.strip()
                if fi_stakeholders_scope.strip():
                    ef["stakeholders_scope"] = fi_stakeholders_scope.strip()
                if fi_stakeholders_report.strip():
                    ef["stakeholders_report"] = fi_stakeholders_report.strip()
                ef["timing"] = timing_val
                ef["size_of_business_impact"] = fi_impact
                ef["confidence_level"] = fi_confidence
                ef["type_of_decision"] = fi_decision_type
                ef["overall_risk_of_doing_nothing"] = fi_risk

                st.session_state.extracted_fields = ef
                st.session_state.intake_submitted = True
                st.rerun()

        st.stop()

    # ── Chat messages (custom renderer — no avatars) ──
    for msg in st.session_state.messages:
        text = msg.get("display_content") or msg.get("content", "")
        # Strip any extraction/output markers that may exist in older saved sessions
        text = clean_response_for_display(text)
        render_message(msg["role"], text)

    # ── Form output (brief generated) ──
    if st.session_state.form_output:
        # Auto-send email on brief generation (first time only)
        has_creds = bool(os.environ.get("GMAIL_ADDRESS") and os.environ.get("GMAIL_APP_PASSWORD"))
        if has_creds and not st.session_state.email_sent:
            proj_name = st.session_state.extracted_fields.get("project_name") or "New Request"
            ok, status_msg = send_intake_email(
                st.session_state.form_output,
                st.session_state.email_output or "",
                proj_name,
                st.session_state.session_id,
            )
            st.session_state.email_sent   = ok
            st.session_state.email_status = (ok, status_msg)

        # ── Warm closing card shown to stakeholder ──
        st.divider()
        st.markdown(
            """
            <div style='background:#F8F1E7;border:1px solid #CFC8C5;border-radius:4px;
                        padding:28px 32px;max-width:560px;margin:0 auto 24px auto;text-align:center;'>
                <div style='font-size:22px;margin-bottom:12px;'>✓</div>
                <div style='font-size:18px;font-weight:700;letter-spacing:-0.3px;
                            color:#131317;margin-bottom:10px;'>You're all set</div>
                <div style='font-size:14px;line-height:1.7;color:#3E474A;'>
                    Thanks for walking me through this. The CRI team will be in touch soon
                    to scope the project and get things moving.<br><br>
                    If anything comes up in the meantime, reach out directly.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Chat input ──
    if prompt := st.chat_input("What's going on with your project?"):
        st.session_state.messages.append(
            {"role": "user", "content": prompt, "display_content": prompt}
        )
        render_message("user", prompt)

        system_prompt = build_system_prompt(
            st.session_state.extracted_fields,
            compute_coverage(st.session_state.extracted_fields),
        )

        api_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages
        ]

        with st.spinner(""):
            response = call_llm(api_messages, system_prompt, api_key or None)

        st.session_state.extracted_fields = extract_fields_from_response(
            response, st.session_state.extracted_fields
        )

        form_out, email_out = extract_form_output(response)
        if form_out:
            # Append the raw transcript as an appendix for CRI researchers
            all_msgs = st.session_state.messages + [{
                "role": "assistant",
                "content": response,
                "display_content": clean_response_for_display(response),
            }]
            transcript = build_transcript_appendix(all_msgs, st.session_state.extracted_fields)
            st.session_state.form_output = form_out + transcript
        if email_out:
            st.session_state.email_output = email_out

        display_text = clean_response_for_display(response)
        render_message("assistant", display_text)

        st.session_state.messages.append({
            "role": "assistant",
            "content": response,
            "display_content": display_text,
        })

        save_session(
            st.session_state.session_id,
            [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
            st.session_state.extracted_fields,
            st.session_state.form_output,
            st.session_state.email_output,
        )

        st.rerun()


if __name__ == "__main__":
    main()
