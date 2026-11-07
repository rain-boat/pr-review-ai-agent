"""PR-wide impact analysis, kept separate from inline code findings."""

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from google.genai import types

from app.gimini import client


ANALYSIS_MODEL = "gemini-3.8-flash"


class ImpactedArea(BaseModel):
    area: str
    description: str
    impact_type: Literal["Direct", "Indirect"]
    related_files: list[str] = Field(default_factory=list)
    reason: str


class ImpactItem(BaseModel):
    status: Literal["Confirmed", "Potential"]
    description: str


class DeveloperBrief(BaseModel):
    developer_context: str
    areas_for_attention: list[str] = Field(default_factory=list)
    reviewer_focus: list[str] = Field(default_factory=list)
    qa_focus: list[str] = Field(default_factory=list)


class PRImpactAnalysis(BaseModel):
    pr_brief: str
    impacted_areas: list[ImpactedArea] = Field(default_factory=list)
    severity: Literal["Critical", "High", "Medium", "Low", "Informational"]
    severity_reason: str
    criticality: Literal["Critical", "High", "Medium", "Low"]
    criticality_reason: str
    overall_risk: Literal["Critical", "High", "Medium", "Low"]
    overall_risk_reason: str
    potential_impacts: list[ImpactItem] = Field(default_factory=list)
    testing_recommendations: list[str] = Field(default_factory=list)
    developer_brief: DeveloperBrief


def _changed_files_context(files: list[dict]) -> str:
    parts = []
    for file in files:
        parts.append(
            f"File: {file.get('filename', '(unknown)')}\n"
            f"Status: {file.get('status', '(unknown)')}\n"
            f"Patch:\n{file.get('patch') or '[patch unavailable]'}"
        )
    return "\n\n".join(parts) or "No changed-file data was supplied."


def build_analysis_prompt(pr_metadata: dict, files: list[dict], review: dict) -> str:
    """Build the PR-level prompt from already collected workflow context."""
    return f"""Analyze this pull request as a whole. This is a separate assessment from line-by-line review; do not recreate or alter its findings.

Use only evidence provided below. Do not invent business requirements. Separate confirmed impacts from potential risks. Severity (risk from a specific change/finding), criticality (importance of the affected functionality), and overall risk are independent judgments. If test coverage, commit messages, or dependency details are unavailable, say so or account for that uncertainty; do not imply they were checked.

Return only a JSON object matching this schema:
{{
  "pr_brief": "concise explanation of what, why when known, affected functionality, expected behavior",
  "impacted_areas": [{{"area":"", "description":"", "impact_type":"Direct|Indirect", "related_files":[], "reason":""}}],
  "severity":"Critical|High|Medium|Low|Informational", "severity_reason":"",
  "criticality":"Critical|High|Medium|Low", "criticality_reason":"",
  "overall_risk":"Critical|High|Medium|Low", "overall_risk_reason":"",
  "potential_impacts":[{{"status":"Confirmed|Potential", "description":""}}],
  "testing_recommendations":[],
  "developer_brief":{{"developer_context":"", "areas_for_attention":[], "reviewer_focus":[], "qa_focus":[]}}
}}

Consider regression scenarios, compatibility, API contracts, dependencies, platform/performance implications, and coverage only where relevant/evidenced. Include sections useful to answer what developers should understand, areas needing attention, reviewer focus, and QA focus.

PR metadata:
{json.dumps(pr_metadata, ensure_ascii=False)}

Existing line-by-line findings (context only):
{json.dumps(review.get('issues', []), ensure_ascii=False)}

Changed files and diffs:
{_changed_files_context(files)}
"""


def _parse_analysis(response_text: str) -> PRImpactAnalysis:
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return PRImpactAnalysis.model_validate_json(cleaned)
    except (ValidationError, ValueError) as exc:
        raise ValueError("Gemini returned an invalid PR impact analysis") from exc


async def analyze_pull_request(pr_metadata: dict, files: list[dict], review: dict) -> PRImpactAnalysis:
    prompt = build_analysis_prompt(pr_metadata, files, review)
    response = client.models.generate_content(
        model=ANALYSIS_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    if not response.text:
        raise ValueError("Gemini returned an empty PR impact analysis")
    return _parse_analysis(response.text)


def render_analysis(analysis: PRImpactAnalysis) -> str:
    data = analysis.model_dump()
    lines = ["## PR Impact Analysis", "", "### PR Brief", "", data["pr_brief"], "", "### Impacted Areas", ""]
    lines += ["| Area | Impact Type | Description | Related Files | Reason |", "|---|---|---|---|---|"]
    for item in data["impacted_areas"]:
        cells = [item["area"], item["impact_type"], item["description"], ", ".join(item["related_files"]), item["reason"]]
        lines.append("| " + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in cells) + " |")
    if not data["impacted_areas"]:
        lines.append("No impacted areas could be identified from the supplied context.")
    lines += ["", "### Severity", "", f"**{data['severity']}** — {data['severity_reason']}", "", "### Criticality", "", f"**{data['criticality']}** — {data['criticality_reason']}", "", "### Overall PR Risk", "", f"**{data['overall_risk']}** — {data['overall_risk_reason']}", "", "### Potential Impact / Regression", ""]
    lines += [f"- **{item['status']}:** {item['description']}" for item in data["potential_impacts"]] or ["- No specific impacts identified from the supplied context."]
    lines += ["", "### Testing Recommendations", ""]
    lines += [f"- {item}" for item in data["testing_recommendations"]] or ["- No specific recommendations returned."]
    brief = data["developer_brief"]
    lines += ["", "### Developer / Reviewer Brief", "", brief["developer_context"], "", "**Areas for attention**"]
    lines += [f"- {item}" for item in brief["areas_for_attention"]] or ["- None identified."]
    lines += ["", "**Reviewer focus**"]
    lines += [f"- {item}" for item in brief["reviewer_focus"]] or ["- None identified."]
    lines += ["", "**QA focus**"]
    lines += [f"- {item}" for item in brief["qa_focus"]] or ["- None identified."]
    return "\n".join(lines)
