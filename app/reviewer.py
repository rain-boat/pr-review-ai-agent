import json
import re

from app.gimini import client


def add_line_numbers_to_patch(patch: str) -> str:
    lines = patch.splitlines()
    result = []

    current_new_line = None

    for line in lines:
        hunk_match = re.match(
            r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@",
            line,
        )

        if hunk_match:
            current_new_line = int(
                hunk_match.group(1)
            )
            result.append(line)
            continue

        if current_new_line is None:
            result.append(line)
            continue

        if line.startswith("+") and not line.startswith("+++"):
            result.append(
                f"NEW_LINE {current_new_line}: {line}"
            )
            current_new_line += 1

        elif line.startswith("-") and not line.startswith("---"):
            result.append(
                f"OLD_LINE: {line}"
            )

        else:
            result.append(
                f"CONTEXT_LINE {current_new_line}: {line}"
            )
            current_new_line += 1

    return "\n".join(result)


def build_review_prompt(files: list[dict]) -> str:
    sections = []

    for file in files:
        filename = file.get("filename", "")
        status = file.get("status", "")
        patch = file.get("patch")

        if not patch:
            continue

        numbered_patch = add_line_numbers_to_patch(
            patch
        )

        sections.append(
            f"""
File: {filename}
Status: {status}

Changed lines:
~~~diff
{numbered_patch}
~~~
"""
        )

    diff = "\n".join(sections)

    prompt = f"""
You are an expert software engineer performing a GitHub Pull Request code review.

Review the following GitHub Pull Request changes.

Focus only on meaningful issues involving:
- Bugs and incorrect behavior
- Security vulnerabilities
- Performance problems
- Error handling
- Maintainability
- Clear code quality problems

Do not report formatting or style issues unless they cause a real problem.

Only report issues supported by the provided code changes.
Do not invent missing context.

IMPORTANT RULES FOR LINE NUMBERS:

1. Every issue MUST have a "line" field.
2. "line" must be an integer.
3. "file" must exactly match one of the provided file paths.
4. "line" must be a NEW_LINE number shown in the provided patch.
5. Never use an OLD_LINE.
6. Never invent a line number.
7. If an issue cannot be attached to a changed NEW_LINE, do not report that issue.

Return ONLY valid JSON.

Do not use Markdown.
Do not add ```json.
Do not add explanations outside the JSON.

Use exactly this structure:

{{
  "issues": [
    {{
      "severity": "high",
      "file": "lib/main.dart",
      "line": 42,
      "title": "Hardcoded API key committed in source code",
      "explanation": "Explain the problem clearly.",
      "suggested_fix": "Explain how to fix it."
    }}
  ]
}}

Allowed severity values:
- critical
- high
- medium
- low

The "line" value MUST be an integer.

If there are no meaningful issues, return:

{{
  "issues": []
}}

Pull Request changes:

{diff}
"""

    return prompt


async def review_files(files: list[dict]) -> dict:
    prompt = build_review_prompt(files)

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
    )

    review_text = response.text.strip()

    try:
        review = json.loads(review_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Gemini returned invalid JSON: {review_text}"
        ) from exc

    if not isinstance(review, dict):
        raise ValueError(
            "Gemini review must be a JSON object"
        )

    if "issues" not in review:
        raise ValueError(
            "Gemini review is missing the 'issues' field"
        )

    return review