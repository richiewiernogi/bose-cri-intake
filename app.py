import streamlit as st
import json
import os
import datetime
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
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
Sharp, warm, direct. You've run hundreds of projects and you know the difference between an intake that produces great work and one that wastes everyone's time. You are a fact-finder, not an advisor. Your job in this conversation is to extract — cleanly and efficiently — what CRI needs to scope and propose the right research.

## ABSOLUTE RULES (never violate these)
- **Never mention methodology to the stakeholder.** Do not say qual, quant, survey, focus group, ethnography, mixed methods, or anything like it. That is CRI's decision. Your job is to understand the business need — not to suggest how it will be answered.
- **Never inject opinions or recommendations** about their strategy, their decisions, or their approach. You are a neutral fact-finder. Curiosity yes, editorializing no.
- **One question per turn, always.** Never list multiple questions. Pick the single sharpest one.
- **No filler.** No "Great question," "Absolutely," "That makes sense." Just engage.

## TONE
Collegial and efficient. Respectful of their time. Think: the researcher they're glad they talked to because you got to the point fast and asked the right things. Confident without being clinical. A little warmth is fine. Humor when it fits naturally. No pleasantries, no throat-clearing — just move it forward.

## THE TWO THINGS THAT MATTER MOST
Everything else in this conversation is secondary to nailing these two:

**1. The business question** — Not the research question. The *business* question. What does the business actually need to know? This is specific, not general. "How do customers feel about Bose" is not a business question. "Which of these two product positioning strategies will resonate better with 25–34 year-old premium audio buyers" is. Push until you have the real one.

**2. The decision this feeds** — What specific decision will be made with this research, and by whom? If they get the answer they're hoping for, what happens next? What gets funded, killed, launched, changed, or presented to whom? This should be concrete and named.

Everything else — audience, existing knowledge, stakes, hypothesis — is important context. But without a clear business question and a clear decision, CRI can't scope or propose anything meaningful.

## HOW YOU CONDUCT THIS CONVERSATION
- **Lead with the business question and decision.** Start there. Get specific. Don't move on until you have something concrete.
- **Ask synthesizing questions**, not data-collection questions. One good question can surface the situation, the stakes, and the urgency simultaneously.
- **Follow the thread that matters**, not the next logical checkbox. If they say something rich, go there.
- **Reflect back** when it helps them get precise. A well-placed "so the core question is really X?" does more than five follow-up questions.
- **Push gently on vagueness** without naming it as vague. Just ask the question that forces precision.
- **Never** say: "let me push on this," "can you clarify," "I want to make sure I understand," or any meta-commentary. Just ask the next question.

## PACING — THIS IS CRITICAL
This conversation should take **4–6 exchanges** for most projects. A VP or C-suite stakeholder has 5 minutes, not 20. Move efficiently.

- Turn 1: Get the business situation and the core question. These often come together if you ask right.
- Turn 2: Lock in the decision — what happens with the research, who makes the call.
- Turn 3: Their current hypothesis / what they already believe or know.
- Turn 4: Who we're studying, any constraints (audience, geography).
- Turn 5 (if needed): Anything genuinely missing that matters for scoping.
- Offer to wrap up as soon as you have enough: *"I think I have what I need — want me to pull this together?"*

Do NOT drag it out to collect every possible piece of information. A tight brief with the essentials is better than a sprawling one. If something's missing, the researcher will ask in scoping.

## WHAT YOU NEED TO UNDERSTAND (internal compass only — not a checklist)
1. **The specific business question** — precise, not general
2. **The decision it feeds** — concrete, named, actionable
3. **Their current hypothesis** — what they already believe, how confident
4. **Who we're studying** — target consumers, geography, meaningful sub-groups
5. **What already exists** — prior data, research, intuition; what gap this fills
6. **The stakes** — how big, what's the risk of not doing it

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
When the stakeholder confirms they're ready to wrap up, generate a research brief using EXACTLY this format. Written FOR the CRI researcher — not the stakeholder. You have a voice. Use it.

The brief has two purposes:
1. **Proposal inputs** — the concrete facts CRI needs to scope and write a proposal: the business question, the decision it feeds, who we're studying, timing, stakes
2. **Prioritization context** — the rationale and judgment layer: what's really going on, how solid the ask is, what to probe in scoping, where this falls in terms of urgency and complexity

Keep these two purposes distinct in the brief. Sections 1–6 are factual. Researcher Notes is where your judgment lives.

===BRIEF_OUTPUT_START===
**Project:** [name and requestor]
**Deadline:** [timing]
**Sponsor:** [if known]
**Stakeholders:** [scoping: X | report-out: Y, if provided]

---

### The Ask

**Business Question**
[The specific business question — not a research question, not a topic area. The precise thing the business needs to know. One or two sentences max. If it's still fuzzy after the conversation, say so honestly and note what you got closest to.]

**Decision It Feeds**
[Concrete and named. What specific decision will this research inform, who makes it, and what changes as a result? If they get the answer they're hoping for, what happens next?]

**The Situation**
[2–3 sentences: what's happening in the business right now that's driving this ask. Why this, why now.]

**Their Current Hypothesis**
[What they believe going in. How confident they seem. What data or gut backs it. Be honest if they sound like they want validation more than insight.]

---

### Research Parameters

**Who We're Studying**
[Target consumers, geography, key sub-groups that matter for the analysis.]

**What We Already Know**
[Prior data, past research, existing intuition. What gap does this project uniquely fill?]

**The Stakes**
[How big is this? What's the risk of not doing it? What metrics or decisions does it touch.

Incorporate the stakeholder's self-assessment naturally — don't list it robotically:
- Business impact: {extracted_fields.get("size_of_business_impact") or "not assessed"}
- Existing knowledge: {extracted_fields.get("confidence_level") or "not assessed"}
- Decision reversibility: {extracted_fields.get("type_of_decision") or "not assessed"}
- Risk of not doing: {extracted_fields.get("overall_risk_of_doing_nothing") or "not assessed"}

If any of these feel inconsistent with what came out in conversation, flag it in Researcher Notes.]

---

### Researcher Notes
[Insider briefing. Professional but casual. First person. You have a take — use it.

Cover all of these:

**The real situation:** What's the actual pressure or political dynamic driving this? What's the subtext?

**Methodology read:** Your honest take on what kind of research this calls for (exploration vs. validation vs. tracking, scale of effort, whether a phased approach makes sense). This is where methodology lives — not in conversation with the stakeholder.

**Where the ask is solid:** What did they clearly articulate? What can we confidently scope from this conversation?

**Where the ask is fuzzy or risky:** Gaps, assumptions that need pressure-testing, hypothesis that sounds like a conclusion, timeline that doesn't match ambition, scope creep risk, want-validation-not-insight warning signs.

**For scoping:** The one or two things the researcher absolutely must nail down before writing a proposal. Specific questions to ask.

Don't be timid. If it's messy, say so. This is the brief the researcher reads before picking up the phone.]
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
# Completed Form Generator
# ---------------------------------------------------------------------------
def generate_completed_form(messages: list, extracted_fields: dict, api_key: str | None) -> str:
    """
    Makes a focused LLM call to fill every field from the original FORM_SCHEMA
    based on what was learned in the intake conversation and pre-form inputs.
    Returns an HTML string of the completed form.
    """
    # Build a condensed transcript for the form-fill prompt
    transcript_lines = []
    for m in messages:
        if m["role"] not in ("user", "assistant"):
            continue
        display = m.get("display_content") or m.get("content", "")
        # Strip internal markers
        for pair in [("===EXTRACTED_START===","===EXTRACTED_END==="),
                     ("===BRIEF_OUTPUT_START===","===BRIEF_OUTPUT_END==="),
                     ("===EMAIL_SUMMARY_START===","===EMAIL_SUMMARY_END===")]:
            while pair[0] in display and pair[1] in display:
                s = display.index(pair[0]); e = display.index(pair[1]) + len(pair[1])
                display = display[:s] + display[e:]
        display = display.strip()
        if display:
            speaker = "STAKEHOLDER" if m["role"] == "user" else "CRI"
            transcript_lines.append(f"{speaker}: {display}")
    transcript = "\n\n".join(transcript_lines)

    # Pre-form data already captured
    preform_data = {k: extracted_fields.get(k) for k in [
        "requestor", "project_name", "sponsor", "stakeholders_scope",
        "stakeholders_report", "timing", "size_of_business_impact",
        "confidence_level", "type_of_decision", "overall_risk_of_doing_nothing"
    ]}

    # Build field list for the prompt
    field_descriptions = []
    for section in FORM_SCHEMA.values():
        for fkey, finfo in section["fields"].items():
            field_descriptions.append(f'  "{fkey}": // {finfo["label"]} — {finfo["description"]}')
    fields_block = "\n".join(field_descriptions)

    form_fill_prompt = f"""You are filling out a structured research intake form on behalf of Bose CRI based on a completed intake conversation.

Below is the conversation transcript and the structured data already collected upfront.

## Pre-form data already collected:
{json.dumps({k: v for k, v in preform_data.items() if v}, indent=2)}

## Intake conversation transcript:
{transcript}

## Your task:
Fill every field below as completely as possible from the conversation. Write in the voice of the stakeholder (first person where appropriate). Be specific and faithful to what they said — don't invent or embellish. If a field was genuinely not addressed, write "Not provided." Don't leave anything blank.

Output ONLY a valid JSON object with exactly these keys:

{{
{fields_block}
}}

Return only the JSON. No commentary, no markdown fences."""

    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=2048,
                messages=[{"role": "user", "content": form_fill_prompt}],
            )
            raw = resp.content[0].text.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                raw = raw.rsplit("```", 1)[0].strip()
            field_values = json.loads(raw)
        except Exception:
            # Fall back to best-effort from extracted_fields
            field_values = {}
    else:
        field_values = {}

    # Merge with extracted_fields as fallback for any missing keys
    for fkey in get_all_field_keys():
        if not field_values.get(fkey):
            ev = extracted_fields.get(fkey)
            if ev:
                field_values[fkey] = ev

    # Render as clean HTML document
    html_parts = ["""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; color: #131317; max-width: 720px; margin: 40px auto; padding: 0 24px; }
  .doc-header { border-bottom: 2px solid #131317; padding-bottom: 14px; margin-bottom: 32px; }
  .doc-header .label { font-size: 11px; letter-spacing: 2px; text-transform: uppercase; color: #B4BEC7; margin-bottom: 4px; }
  .doc-header h1 { font-size: 24px; font-weight: 900; margin: 0; }
  .section { margin-bottom: 32px; }
  .section-title { font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
                   color: #B4BEC7; border-bottom: 1px solid #E8E3DE; padding-bottom: 8px; margin-bottom: 20px; }
  .field { margin-bottom: 18px; }
  .field-label { font-size: 11px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase;
                 color: #3E474A; margin-bottom: 4px; }
  .field-priority-critical { border-left: 3px solid #131317; padding-left: 10px; }
  .field-priority-important { border-left: 3px solid #B4BEC7; padding-left: 10px; }
  .field-priority-nice_to_have { border-left: 3px solid #E8E3DE; padding-left: 10px; }
  .field-value { font-size: 14px; line-height: 1.7; color: #131317; }
  .field-value.empty { color: #B4BEC7; font-style: italic; }
  .footer { margin-top: 48px; padding-top: 16px; border-top: 1px solid #E8E3DE;
            font-size: 11px; color: #B4BEC7; }
</style>
</head>
<body>
<div class="doc-header">
  <div class="label">Bose · Consumer Research &amp; Insights</div>
  <h1>Research Intake Form</h1>
</div>
"""]

    for section_key, section in FORM_SCHEMA.items():
        html_parts.append(f'<div class="section">')
        html_parts.append(f'<div class="section-title">{section["section_label"]}</div>')
        for fkey, finfo in section["fields"].items():
            value = field_values.get(fkey, "")
            priority = finfo.get("priority", "nice_to_have")
            is_empty = not value or value.strip().lower() in ("not provided", "null", "none", "")
            value_class = "field-value empty" if is_empty else "field-value"
            display_value = value if (value and not is_empty) else "Not provided"
            html_parts.append(
                f'<div class="field field-priority-{priority}">'
                f'<div class="field-label">{finfo["label"]}</div>'
                f'<div class="{value_class}">{display_value}</div>'
                f'</div>'
            )
        html_parts.append('</div>')

    html_parts.append('<div class="footer">Generated via CRI Research Intake · Bose Consumer Research &amp; Insights</div>')
    html_parts.append("</body></html>")

    return "\n".join(html_parts)


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


def get_conversation_phase(extracted_fields: dict, message_count: int) -> tuple[str, str]:
    """
    Return (phase_label, phase_hint) based on what's been captured so far.
    Drives the ambient progress cue shown to the stakeholder — not a percentage,
    just a quiet orientation signal.
    """
    core_fields = [
        extracted_fields.get("business_context"),
        extracted_fields.get("primary_business_questions"),
        extracted_fields.get("intended_decision_action"),
        extracted_fields.get("core_audience"),
        extracted_fields.get("current_hypothesis") or extracted_fields.get("existing_information"),
    ]
    filled = sum(1 for f in core_fields if f)

    if message_count == 0:
        return "", ""
    elif filled == 0:
        return "Getting started", "Just getting a feel for the project"
    elif filled <= 1:
        return "Early stages", "Still mapping the situation"
    elif filled == 2:
        return "Getting there", "Building a clearer picture"
    elif filled == 3:
        return "Good shape", "Filling in the last few pieces"
    elif filled == 4:
        return "Almost there", "Nearly ready to wrap up"
    else:
        return "Ready to write up", "Tell me when you want to wrap and I'll pull this together"


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
def send_intake_email(form_text: str, email_summary: str, project_name: str, session_id: str,
                      completed_form_html: str | None = None):
    """
    Send the research brief to CRI via Gmail SMTP, with the completed original
    intake form attached as an HTML file.
    Returns (success: bool, message: str).
    """
    gmail_address  = os.environ.get("GMAIL_ADDRESS", "").strip()
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    recipient      = os.environ.get("CRI_RECIPIENT", "erich_wiernasz@bose.com").strip()

    if not gmail_address or not gmail_password:
        return False, "Email credentials not configured. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to your .env file."

    subject = f"Research Request: {project_name or 'New Request'} [{session_id}]"

    # Convert markdown brief to HTML for email body
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

{'<div style="background: #F8F1E7; border: 1px solid #CFC8C5; padding: 12px 16px; margin-bottom: 24px; border-radius: 2px; font-size: 13px; color: #3E474A;">📎 <strong>Completed intake form attached</strong> — see <em>CRI_IntakeForm_{session_id}.html</em></div>' if completed_form_html else ''}

<div style="font-size: 14px; line-height: 1.8;">
{brief_html_content}
</div>

<div style="margin-top: 32px; padding-top: 16px; border-top: 1px solid #CFC8C5; font-size: 11px; color: #B4BEC7;">
  Submitted via CRI Research Intake · Session ID: {session_id}
</div>
</body></html>
"""

    plain_body = f"CRI Research Request: {project_name}\n\n{email_summary}\n\n---\n\n{form_text}\n\nSession ID: {session_id}"

    # ── Outer container: mixed (supports both body alternatives + attachments) ──
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = f"CRI Intake Assistant <{gmail_address}>"
    msg["To"]      = recipient
    msg["Reply-To"] = gmail_address

    # ── Inner alternative part for plain/html body ──
    body_part = MIMEMultipart("alternative")
    body_part.attach(MIMEText(plain_body, "plain"))
    body_part.attach(MIMEText(html_body, "html"))
    msg.attach(body_part)

    # ── Attach completed intake form as HTML file ──
    if completed_form_html:
        attachment = MIMEBase("text", "html")
        attachment.set_payload(completed_form_html.encode("utf-8"))
        encoders.encode_base64(attachment)
        filename = f"CRI_IntakeForm_{session_id}.html"
        attachment.add_header("Content-Disposition", "attachment", filename=filename)
        attachment.add_header("Content-Type", "text/html; charset=utf-8")
        msg.attach(attachment)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, recipient, msg.as_string())
        return True, "Brief and intake form sent to CRI successfully."
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
            for key in ["messages", "extracted_fields", "session_id", "form_output", "email_output", "email_sent", "email_status", "intake_submitted", "completed_form"]:
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
    if "completed_form" not in st.session_state:
        st.session_state.completed_form = None

    # ── Main header ──
    st.markdown(
        """
        <div class="main-header">
            <div class="brand-label">Bose · Consumer Research & Insights</div>
            <h1>Research Intake</h1>
            <div class="subtitle">A few questions to help CRI scope the right research for you.</div>
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

            st.markdown(
                "<div style='font-size:11px;color:#7F8891;text-align:center;margin-top:8px;margin-bottom:-4px;'>"
                "Use <strong>Tab</strong> to move between fields. Click the button below when you're ready.</div>",
                unsafe_allow_html=True,
            )
            submitted = st.form_submit_button("Start the conversation →", type="primary", use_container_width=True)

        if submitted:
            # Catch accidental submits — require name + at least project name or sponsor
            missing = []
            if not fi_name.strip():
                missing.append("Your Name")
            if not fi_project.strip() and not fi_sponsor.strip():
                missing.append("Project Name or Executive Sponsor")
            if missing:
                st.error(f"Please fill in: {', '.join(missing)}. Use Tab to move between fields, then click the button when ready.")
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

                # Seed the conversation with a structured opening question
                proj_display = fi_project.strip() or "this"
                opening = (
                    f"Thanks, {fi_name.strip().split()[0]}. "
                    f"Let's get into it.\n\n"
                    f"What's the specific business question you're trying to answer with {proj_display}? "
                    f"Not the broad topic — the precise thing the business needs to know to make a decision."
                )
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": opening,
                    "display_content": opening,
                })

                st.rerun()

        st.stop()

    # ── Chat messages (custom renderer — no avatars) ──
    for msg in st.session_state.messages:
        text = msg.get("display_content") or msg.get("content", "")
        # Strip any extraction/output markers that may exist in older saved sessions
        text = clean_response_for_display(text)
        render_message(msg["role"], text)

    # ── Ambient progress signal (shown after messages, before brief, when conversation is active) ──
    if st.session_state.messages and not st.session_state.form_output:
        user_turns = sum(1 for m in st.session_state.messages if m["role"] == "user")
        phase_label, phase_hint = get_conversation_phase(
            st.session_state.extracted_fields, user_turns
        )
        if phase_label:
            st.markdown(
                f"<div style='text-align:center;padding:16px 0 4px 0;'>"
                f"<span style='display:inline-block;font-size:11px;font-weight:600;"
                f"letter-spacing:1.5px;text-transform:uppercase;color:#B4BEC7;"
                f"border:1px solid #E8E3DE;border-radius:20px;padding:5px 14px;'>"
                f"{phase_label}</span></div>",
                unsafe_allow_html=True,
            )

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
                completed_form_html=st.session_state.completed_form,
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
    if prompt := st.chat_input("Type your response here…"):
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

            # Generate the completed original intake form (as HTML, for email attachment)
            if st.session_state.completed_form is None:
                with st.spinner("Generating completed intake form…"):
                    st.session_state.completed_form = generate_completed_form(
                        all_msgs,
                        st.session_state.extracted_fields,
                        api_key or None,
                    )
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
