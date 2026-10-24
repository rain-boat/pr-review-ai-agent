import hashlib
import json
import os

import asyncpg
from dotenv import load_dotenv


load_dotenv()


DATABASE_URL = os.getenv(
    "DATABASE_URL"
)


def build_issue_fingerprint(
    issue: dict,
) -> str:
    """
    Create a stable fingerprint for an issue.

    We use the file and issue title rather than the
    line number because a line can move between commits.
    """

    file = str(
        issue.get("file", "")
    ).strip()

    title = str(
        issue.get("title", "")
    ).strip().lower()

    raw = f"{file}|{title}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


async def get_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured"
        )

    return await asyncpg.connect(
        DATABASE_URL
    )


async def get_active_issue_fingerprints(
    repository: str,
    pull_number: int,
) -> set[str]:
    """
    Get issues that are currently active for this PR.
    """

    connection = await get_connection()

    try:
        rows = await connection.fetch(
            """
            SELECT fingerprint
            FROM ai_review_issues
            WHERE repository = $1
              AND pull_number = $2
              AND active = TRUE
            """,
            repository,
            pull_number,
        )

        return {
            row["fingerprint"]
            for row in rows
        }

    finally:
        await connection.close()


async def filter_new_issues(
    repository: str,
    pull_number: int,
    issues: list[dict],
) -> list[dict]:
    """
    Return only issues that have not already been
    reported as active for this PR.
    """

    active_fingerprints = (
        await get_active_issue_fingerprints(
            repository=repository,
            pull_number=pull_number,
        )
    )

    new_issues = []

    for issue in issues:
        fingerprint = (
            build_issue_fingerprint(issue)
        )

        if fingerprint in active_fingerprints:
            print(
                "Skipping duplicate issue:"
            )

            print(
                f"  {issue.get('file')}:"
                f"{issue.get('line')} - "
                f"{issue.get('title')}"
            )

            continue

        new_issues.append(issue)

    return new_issues


async def save_active_issues(
    repository: str,
    pull_number: int,
    issues: list[dict],
):
    """
    Save the issues found in the current review.

    Existing issues remain active.
    New issues are inserted.
    """

    connection = await get_connection()

    try:
        for issue in issues:
            fingerprint = (
                build_issue_fingerprint(issue)
            )

            issue_json = json.dumps(
                issue
            )

            await connection.execute(
                """
                INSERT INTO ai_review_issues (
                    repository,
                    pull_number,
                    fingerprint,
                    file,
                    line,
                    title,
                    issue_json,
                    active
                )
                VALUES (
                    $1,
                    $2,
                    $3,
                    $4,
                    $5,
                    $6,
                    $7::jsonb,
                    TRUE
                )
                ON CONFLICT (
                    repository,
                    pull_number,
                    fingerprint
                )
                DO UPDATE SET
                    file = EXCLUDED.file,
                    line = EXCLUDED.line,
                    title = EXCLUDED.title,
                    issue_json = EXCLUDED.issue_json,
                    active = TRUE,
                    updated_at = NOW()
                """,
                repository,
                pull_number,
                fingerprint,
                issue.get("file", ""),
                issue.get("line"),
                issue.get("title", ""),
                issue_json,
            )

    finally:
        await connection.close()


async def mark_missing_issues_inactive(
    repository: str,
    pull_number: int,
    current_issues: list[dict],
):
    """
    Mark previously active issues as inactive when
    Gemini no longer reports them.
    """

    current_fingerprints = {
        build_issue_fingerprint(issue)
        for issue in current_issues
    }

    connection = await get_connection()

    try:
        rows = await connection.fetch(
            """
            SELECT id, fingerprint
            FROM ai_review_issues
            WHERE repository = $1
              AND pull_number = $2
              AND active = TRUE
            """,
            repository,
            pull_number,
        )

        for row in rows:
            if (
                row["fingerprint"]
                not in current_fingerprints
            ):
                await connection.execute(
                    """
                    UPDATE ai_review_issues
                    SET active = FALSE,
                        updated_at = NOW()
                    WHERE id = $1
                    """,
                    row["id"],
                )

    finally:
        await connection.close()