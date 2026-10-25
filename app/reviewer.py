import json
import re

from google.genai import types

from app.gimini import client
from app.repo_workspace import RepoWorkspace


REVIEW_MODEL = "gemini-3.8-flash"
MAX_TOOL_ROUNDS = 12


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


def build_changed_files_section(files: list[dict]) -> str:
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

    return "\n".join(sections)


def review_tools() -> list[types.Tool]:
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="fetch_repo",
                    description=(
                        "Clone or update the pull request "
                        "repository at the head commit. "
                        "Call this before search_code or "
                        "read_file."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={},
                    ),
                ),
                types.FunctionDeclaration(
                    name="search_code",
                    description=(
                        "Search the cloned repository for "
                        "callers or usages of a method, "
                        "class, or symbol. Use this to find "
                        "unchanged files that may break."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "query": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "Text or regex to search, "
                                    "for example a method name."
                                ),
                            ),
                            "path": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "Optional subdirectory or "
                                    "file to limit the search."
                                ),
                            ),
                        },
                        required=["query"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="read_file",
                    description=(
                        "Read a file from the cloned "
                        "repository. Path is relative to "
                        "the repo root."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "path": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "File path relative to "
                                    "the repository root."
                                ),
                            ),
                            "start_line": types.Schema(
                                type=types.Type.INTEGER,
                                description="First line to read.",
                            ),
                            "end_line": types.Schema(
                                type=types.Type.INTEGER,
                                description="Last line to read.",
                            ),
                        },
                        required=["path"],
                    ),
                ),
            ]
        )
    ]


def execute_tool(
    workspace: RepoWorkspace,
    name: str,
    args: dict,
) -> str:
    if name == "fetch_repo":
        return workspace.fetch_repo()

    if name == "search_code":
        return workspace.search_code(
            query=args.get("query", ""),
            path=args.get("path", "") or "",
        )

    if name == "read_file":
        start_line = args.get("start_line", 1) or 1
        end_line = args.get("end_line")

        return workspace.read_file(
            path=args.get("path", ""),
            start_line=int(start_line),
            end_line=(
                int(end_line)
                if end_line is not None
                else None
            ),
        )

    return f"Unknown tool: {name}"


def build_review_prompt(files: list[dict]) -> str:
    diff = build_changed_files_section(files)

    return f"""
You are an expert software engineer performing a GitHub Pull Request code review.

You cannot run shell commands. You may only use these tools:
- fetch_repo
- search_code
- read_file

Workflow:
1. Call fetch_repo so the PR head commit is available locally.
2. From the changed methods/classes, call search_code to find callers in other files.
3. Call read_file on relevant callers if you need more context.
4. Then return the final JSON review.

Focus only on meaningful issues involving:
- Bugs and incorrect behavior
- Breakage in callers of changed methods
- Security vulnerabilities
- Performance problems
- Error handling
- Maintainability
- Clear code quality problems

Do not report formatting or style issues unless they cause a real problem.
Do not invent missing context. If you need caller context, use the tools.

IMPORTANT RULES FOR LINE NUMBERS:

1. Every issue MUST have a "line" field.
2. "line" must be an integer.
3. "file" must exactly match one of the provided CHANGED file paths.
4. "line" must be a NEW_LINE number shown in the provided patch.
5. Never use an OLD_LINE.
6. Never invent a line number.
7. If a caller may break, attach the issue to the changed method's NEW_LINE and name the caller in the explanation.
8. If an issue cannot be attached to a changed NEW_LINE, do not report that issue.

When you are done using tools, return ONLY valid JSON.

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


def parse_review_json(review_text: str) -> dict:
    cleaned = review_text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
        )
        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

    try:
        review = json.loads(cleaned)
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


def collect_function_calls(response) -> list:
    calls = getattr(response, "function_calls", None)

    if calls:
        return list(calls)

    candidates = getattr(response, "candidates", None) or []

    if not candidates:
        return []

    content = candidates[0].content
    parts = getattr(content, "parts", None) or []
    found = []

    for part in parts:
        function_call = getattr(part, "function_call", None)

        if function_call and getattr(function_call, "name", None):
            found.append(function_call)

    return found


async def review_files(
    files: list[dict],
    owner: str,
    repo: str,
    commit_id: str,
    clone_url: str,
    access_token: str,
    pull_number: int,
) -> dict:
    workspace = RepoWorkspace(
        owner=owner,
        repo=repo,
        commit_id=commit_id,
        clone_url=clone_url,
        access_token=access_token,
        pull_number=pull_number,
    )

    prompt = build_review_prompt(files)
    contents = [prompt]
    tools = review_tools()
    config = types.GenerateContentConfig(
        tools=tools,
    )

    review_text = ""

    for round_number in range(MAX_TOOL_ROUNDS):
        response = client.models.generate_content(
            model=REVIEW_MODEL,
            contents=contents,
            config=config,
        )

        function_calls = collect_function_calls(response)

        if not function_calls:
            review_text = (response.text or "").strip()
            break

        contents.append(response.candidates[0].content)

        function_response_parts = []

        for call in function_calls:
            args = dict(call.args or {})

            print(
                f"Gemini tool call [{round_number + 1}]: "
                f"{call.name} {args}"
            )

            try:
                result = execute_tool(
                    workspace=workspace,
                    name=call.name,
                    args=args,
                )
            except Exception as exc:
                result = f"Tool error: {exc}"

            print(
                f"Tool result [{call.name}]: "
                f"{result[:500]}"
            )

            function_response_parts.append(
                types.Part.from_function_response(
                    name=call.name,
                    response={
                        "result": result,
                    },
                )
            )

        contents.append(
            types.Content(
                role="user",
                parts=function_response_parts,
            )
        )
    else:
        raise ValueError(
            "Gemini used too many tool calls "
            "without returning a review."
        )

    if not review_text:
        raise ValueError(
            "Gemini returned an empty review."
        )

    return parse_review_json(review_text)
