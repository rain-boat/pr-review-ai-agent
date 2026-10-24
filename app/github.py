# import os
# import time

# import httpx
# import jwt
# from dotenv import load_dotenv


# load_dotenv()


# GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")

# PRIVATE_KEY_PATH = os.getenv(
#     "GITHUB_PRIVATE_KEY_PATH",
#     "github-app.pem",
# )

# GITHUB_API_URL = "https://api.github.com"


# def create_app_jwt() -> str:
#     if not GITHUB_APP_ID:
#         raise RuntimeError(
#             "GITHUB_APP_ID is not configured"
#         )

#     with open(
#         PRIVATE_KEY_PATH,
#         "r",
#     ) as private_key_file:
#         private_key = private_key_file.read()

#     now = int(time.time())

#     payload = {
#         "iat": now - 60,
#         "exp": now + (10 * 60),
#         "iss": GITHUB_APP_ID,
#     }

#     return jwt.encode(
#         payload,
#         private_key,
#         algorithm="RS256",
#     )


# async def get_installation_access_token(
#     installation_id: int,
# ) -> str:
#     app_jwt = create_app_jwt()

#     url = (
#         f"{GITHUB_API_URL}/app/installations/"
#         f"{installation_id}/access_tokens"
#     )

#     headers = {
#         "Authorization": f"Bearer {app_jwt}",
#         "Accept": "application/vnd.github+json",
#     }

#     async with httpx.AsyncClient() as client:
#         response = await client.post(
#             url,
#             headers=headers,
#         )

#     response.raise_for_status()

#     return response.json()["token"]


# async def get_latest_open_pull_request(
#     installation_id: int,
#     owner: str,
#     repo: str,
# ) -> dict:
#     access_token = (
#         await get_installation_access_token(
#             installation_id
#         )
#     )

#     url = (
#         f"{GITHUB_API_URL}/repos/"
#         f"{owner}/{repo}/pulls"
#     )

#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "Accept": "application/vnd.github+json",
#     }

#     params = {
#         "state": "open",
#         "sort": "updated",
#         "direction": "desc",
#         "per_page": 1,
#     }

#     async with httpx.AsyncClient() as client:
#         response = await client.get(
#             url,
#             headers=headers,
#             params=params,
#         )

#     response.raise_for_status()

#     pull_requests = response.json()

#     if not pull_requests:
#         raise RuntimeError(
#             f"No open pull requests found in "
#             f"{owner}/{repo}"
#         )

#     return pull_requests[0]


# async def get_pull_request_files(
#     installation_id: int,
#     owner: str,
#     repo: str,
#     pull_number: int,
# ) -> list[dict]:
#     access_token = (
#         await get_installation_access_token(
#             installation_id
#         )
#     )

#     url = (
#         f"{GITHUB_API_URL}/repos/"
#         f"{owner}/{repo}/pulls/"
#         f"{pull_number}/files"
#     )

#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "Accept": "application/vnd.github+json",
#     }

#     async with httpx.AsyncClient() as client:
#         response = await client.get(
#             url,
#             headers=headers,
#         )

#     response.raise_for_status()

#     return response.json()


# def build_inline_comment(
#     issue: dict,
# ) -> dict:
#     return {
#         "path": issue["file"],
#         "line": int(issue["line"]),
#         "side": "RIGHT",
#         "body": (
#             f"**{issue['severity'].upper()} — "
#             f"{issue['title']}**\n\n"
#             f"{issue['explanation']}\n\n"
#             f"**Suggested fix:** "
#             f"{issue['suggested_fix']}"
#         ),
#     }


# async def create_pull_request_review(
#     installation_id: int,
#     owner: str,
#     repo: str,
#     pull_number: int,
#     commit_id: str,
#     issues: list[dict],
# ) -> dict:
#     access_token = (
#         await get_installation_access_token(
#             installation_id
#         )
#     )

#     url = (
#         f"{GITHUB_API_URL}/repos/"
#         f"{owner}/{repo}/pulls/"
#         f"{pull_number}/reviews"
#     )

#     comments = []

#     for issue in issues:
#         comments.append(
#             build_inline_comment(issue)
#         )

#     payload = {
#         "commit_id": commit_id,
#         "body": (
#             "## 🤖 AI Code Review\n\n"
#             f"Found **{len(issues)} issue(s)**. "
#             "Inline comments are attached to "
#             "the relevant changed lines."
#         ),
#         "event": "COMMENT",
#         "comments": comments,
#     }

#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "Accept": "application/vnd.github+json",
#     }

#     async with httpx.AsyncClient() as client:
#         response = await client.post(
#             url,
#             headers=headers,
#             json=payload,
#         )

#     response.raise_for_status()

#     return response.json()

import os
import time

import httpx
import jwt
from dotenv import load_dotenv


load_dotenv()


GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")

PRIVATE_KEY_PATH = os.getenv(
    "GITHUB_PRIVATE_KEY_PATH",
    "github-app.pem",
)

GITHUB_API_URL = "https://api.github.com"


def create_app_jwt() -> str:
    if not GITHUB_APP_ID:
        raise RuntimeError(
            "GITHUB_APP_ID is not configured"
        )

    with open(
        PRIVATE_KEY_PATH,
        "r",
    ) as private_key_file:
        private_key = private_key_file.read()

    now = int(time.time())

    payload = {
        "iat": now - 60,
        "exp": now + (10 * 60),
        "iss": GITHUB_APP_ID,
    }

    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
    )


async def get_installation_access_token(
    installation_id: int,
) -> str:
    app_jwt = create_app_jwt()

    url = (
        f"{GITHUB_API_URL}/app/installations/"
        f"{installation_id}/access_tokens"
    )

    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=headers,
        )

    response.raise_for_status()

    return response.json()["token"]


async def get_latest_open_pull_request(
    installation_id: int,
    owner: str,
    repo: str,
) -> dict:
    access_token = (
        await get_installation_access_token(
            installation_id
        )
    )

    url = (
        f"{GITHUB_API_URL}/repos/"
        f"{owner}/{repo}/pulls"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }

    params = {
        "state": "open",
        "sort": "updated",
        "direction": "desc",
        "per_page": 1,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers=headers,
            params=params,
        )

    response.raise_for_status()

    pull_requests = response.json()

    if not pull_requests:
        raise RuntimeError(
            f"No open pull requests found in "
            f"{owner}/{repo}"
        )

    return pull_requests[0]


async def get_pull_request_files(
    installation_id: int,
    owner: str,
    repo: str,
    pull_number: int,
) -> list[dict]:
    access_token = (
        await get_installation_access_token(
            installation_id
        )
    )

    url = (
        f"{GITHUB_API_URL}/repos/"
        f"{owner}/{repo}/pulls/"
        f"{pull_number}/files"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers=headers,
        )

    response.raise_for_status()

    return response.json()


async def create_ai_review_check(
    installation_id: int,
    owner: str,
    repo: str,
    commit_id: str,
) -> int:
    """
    Create a GitHub Check Run showing that
    the AI review is currently in progress.

    Returns the GitHub check run ID.
    """

    access_token = (
        await get_installation_access_token(
            installation_id
        )
    )

    url = (
        f"{GITHUB_API_URL}/repos/"
        f"{owner}/{repo}/check-runs"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }

    payload = {
        "name": "AI Code Review",
        "head_sha": commit_id,
        "status": "in_progress",
        "started_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
        "output": {
            "title": "AI review in progress",
            "summary": (
                "🤖 Gemini is currently reviewing "
                "the Pull Request."
            ),
        },
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=headers,
            json=payload,
        )

    response.raise_for_status()

    return response.json()["id"]


async def complete_ai_review_check(
    installation_id: int,
    owner: str,
    repo: str,
    check_run_id: int,
    issues_count: int,
) -> dict:
    """
    Mark the AI review Check Run as completed.
    """

    access_token = (
        await get_installation_access_token(
            installation_id
        )
    )

    url = (
        f"{GITHUB_API_URL}/repos/"
        f"{owner}/{repo}/check-runs/"
        f"{check_run_id}"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }

    payload = {
        "status": "completed",
        "completed_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
        "conclusion": "success",
        "output": {
            "title": "AI review completed",
            "summary": (
                f"🤖 AI review completed. "
                f"Found {issues_count} issue(s)."
            ),
        },
    }

    async with httpx.AsyncClient() as client:
        response = await client.patch(
            url,
            headers=headers,
            json=payload,
        )

    response.raise_for_status()

    return response.json()


def build_inline_comment(
    issue: dict,
) -> dict:
    return {
        "path": issue["file"],
        "line": int(issue["line"]),
        "side": "RIGHT",
        "body": (
            f"**{issue['severity'].upper()} — "
            f"{issue['title']}**\n\n"
            f"{issue['explanation']}\n\n"
            f"**Suggested fix:** "
            f"{issue['suggested_fix']}"
        ),
    }


async def create_pull_request_review(
    installation_id: int,
    owner: str,
    repo: str,
    pull_number: int,
    commit_id: str,
    issues: list[dict],
) -> dict:
    access_token = (
        await get_installation_access_token(
            installation_id
        )
    )

    url = (
        f"{GITHUB_API_URL}/repos/"
        f"{owner}/{repo}/pulls/"
        f"{pull_number}/reviews"
    )

    comments = []

    for issue in issues:
        comments.append(
            build_inline_comment(issue)
        )

    payload = {
        "commit_id": commit_id,
        "body": (
            "## 🤖 AI Code Review\n\n"
            f"Found **{len(issues)} issue(s)**. "
            "Inline comments are attached to "
            "the relevant changed lines."
        ),
        "event": "COMMENT",
        "comments": comments,
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=headers,
            json=payload,
        )

    response.raise_for_status()

    return response.json()