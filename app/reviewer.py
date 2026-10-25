import json
import re

from google.genai import types

from app.gimini import client
from app.repo_workspace import RepoWorkspace


REVIEW_MODEL = "gemini-3.8-flash"
DEFAULT_TOOL_ROUNDS = 12
MAX_TOOL_ROUNDS = 32


def calculate_tool_round_limit(files: list[dict]) -> tuple[int, int]:
    """Return the round budget and total changed lines for a PR diff."""
    changed_lines = 0

    for file in files:
        patch = file.get("patch") or ""
        for line in patch.splitlines():
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                changed_lines += 1

    if changed_lines <= 100:
        return DEFAULT_TOOL_ROUNDS, changed_lines
    if changed_lines <= 500:
        return 20, changed_lines
    if changed_lines <= 1000:
        return 28, changed_lines
    return MAX_TOOL_ROUNDS, changed_lines


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
                types.FunctionDeclaration(
                    name="inspect_repo",
                    description=(
                        "Run several independent repository searches "
                        "and read several relevant files in one tool call. "
                        "Use this after fetch_repo to save tool rounds. "
                        "Limit each request to the most relevant symbols/files."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "searches": types.Schema(
                                type=types.Type.ARRAY,
                                description="Up to 12 independent code searches.",
                                items=types.Schema(
                                    type=types.Type.OBJECT,
                                    properties={
                                        "query": types.Schema(type=types.Type.STRING),
                                        "path": types.Schema(type=types.Type.STRING),
                                    },
                                    required=["query"],
                                ),
                            ),
                            "files": types.Schema(
                                type=types.Type.ARRAY,
                                description="Up to 12 relevant files to read.",
                                items=types.Schema(
                                    type=types.Type.OBJECT,
                                    properties={
                                        "path": types.Schema(type=types.Type.STRING),
                                        "start_line": types.Schema(type=types.Type.INTEGER),
                                        "end_line": types.Schema(type=types.Type.INTEGER),
                                    },
                                    required=["path"],
                                ),
                            ),
                        },
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

    if name == "inspect_repo":
        searches = args.get("searches", [])
        files = args.get("files", [])
        results = []

        if not isinstance(searches, list) or not isinstance(files, list):
            return "inspect_repo expects 'searches' and 'files' arrays."

        for search in searches[:12]:
            if not isinstance(search, dict):
                continue
            query = str(search.get("query", ""))
            path = str(search.get("path", "") or "")
            results.append(
                f"### Search: {query} (path: {path or '.'})\n"
                f"{workspace.search_code(query=query, path=path)}"
            )

        for file in files[:12]:
            if not isinstance(file, dict):
                continue
            path = str(file.get("path", ""))
            start_line = int(file.get("start_line", 1) or 1)
            end_line = file.get("end_line")
            file_result = workspace.read_file(
                path=path,
                start_line=start_line,
                end_line=int(end_line) if end_line is not None else None,
            )
            results.append(
                f"### File: {path}\n"
                f"{file_result}"
            )

        if not results:
            return "Provide at least one search or file to inspect."

        output = "\n\n".join(results)
        max_output_chars = 30000
        if len(output) > max_output_chars:
            output = output[:max_output_chars] + "\n...batch output truncated..."
        return output

    return f"Unknown tool: {name}"


def build_review_prompt(files: list[dict]) -> str:
    diff = build_changed_files_section(files)
    tool_round_limit, changed_lines = calculate_tool_round_limit(files)

    return f"""
You are an expert software engineer performing a GitHub Pull Request code review.

You cannot run shell commands. You may only use these tools:
- fetch_repo
- search_code
- read_file
- inspect_repo (batch several searches and file reads in one call)

Workflow:
1. Call fetch_repo so the PR head commit is available locally.
2. Identify the changed symbols that could affect callers or behavior.
3. Batch independent searches and relevant file reads into one inspect_repo call. Use focused searches and read only files needed to confirm likely issues.
4. If the results reveal a new lead, batch the next group of searches/reads together. Do not repeat searches already answered.
5. Return the final JSON review as soon as there is enough evidence; use the full budget only when needed.

The current budget is {tool_round_limit} model/tool-response rounds for {changed_lines} changed lines (maximum budget: {MAX_TOOL_ROUNDS}). The limit counts model/tool-response cycles, not individual operations inside inspect_repo. Each inspect_repo call can contain up to 12 searches and 12 file reads.

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

    tool_round_limit, changed_lines = calculate_tool_round_limit(files)
    print(
        f"Gemini tool budget: {tool_round_limit} rounds "
        f"for {changed_lines} changed lines"
    )

    review_text = ""

    for round_number in range(tool_round_limit):
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
            f"Gemini used too many tool rounds "
            f"(limit: {tool_round_limit}) "
            "without returning a review."
        )

    if not review_text:
        raise ValueError(
            "Gemini returned an empty review."
        )

    return parse_review_json(review_text)
