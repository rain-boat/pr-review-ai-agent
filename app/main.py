# import os

# from dotenv import load_dotenv
# from fastapi import FastAPI, Request

# from app.github import (
#     complete_ai_review_check,
#     create_ai_review_check,
#     create_pull_request_review,
#     get_pull_request_files,
# )
# from app.reviewer import review_files


# load_dotenv()


# app = FastAPI(
#     title="PR Review Agent",
#     description="AI-powered GitHub Pull Request reviewer",
#     version="0.1.0",
# )


# @app.get("/")
# async def root():
#     return {
#         "message": "PR Review Agent is running"
#     }


# @app.get("/health")
# async def health():
#     return {
#         "status": "healthy"
#     }


# async def review_pull_request(
#     installation_id: int,
#     owner: str,
#     repo: str,
#     pull_number: int,
#     commit_id: str,
# ):
#     print("=" * 60)
#     print(
#         f"Starting AI review for PR #{pull_number}"
#     )
#     print(
#         f"Repository: {owner}/{repo}"
#     )
#     print(
#         f"Commit: {commit_id}"
#     )
#     print("=" * 60)

#     # --------------------------------------------------
#     # 1. Create GitHub Check Run
#     # --------------------------------------------------

#     check_run_id = await create_ai_review_check(
#         installation_id=installation_id,
#         owner=owner,
#         repo=repo,
#         commit_id=commit_id,
#     )

#     print(
#         f"AI review check created: "
#         f"{check_run_id}"
#     )

#     try:
#         # --------------------------------------------------
#         # 2. Get changed files
#         # --------------------------------------------------

#         files = await get_pull_request_files(
#             installation_id=installation_id,
#             owner=owner,
#             repo=repo,
#             pull_number=pull_number,
#         )

#         print(
#             f"Changed files: {len(files)}"
#         )

#         # --------------------------------------------------
#         # 3. Send files to Gemini
#         # --------------------------------------------------

#         review = await review_files(files)

#         issues = review.get(
#             "issues",
#             []
#         )

#         print(
#             f"Gemini found {len(issues)} issue(s)"
#         )

#         # --------------------------------------------------
#         # 4. No issues
#         # --------------------------------------------------

#         if not issues:
#             await complete_ai_review_check(
#                 installation_id=installation_id,
#                 owner=owner,
#                 repo=repo,
#                 check_run_id=check_run_id,
#                 issues_count=0,
#             )

#             print(
#                 f"No issues found for PR "
#                 f"#{pull_number}"
#             )

#             return {
#                 "status": "completed",
#                 "issues": 0,
#                 "inline_comments": 0,
#             }

#         # --------------------------------------------------
#         # 5. Validate issues
#         # --------------------------------------------------

#         valid_issues = []

#         for issue in issues:
#             file = issue.get("file")
#             line = issue.get("line")

#             if not file:
#                 print(
#                     "Skipping issue without file"
#                 )
#                 continue

#             if not isinstance(line, int):
#                 print(
#                     "Skipping issue without valid "
#                     f"line: {issue}"
#                 )
#                 continue

#             valid_issues.append(issue)

#         # --------------------------------------------------
#         # 6. Gemini found issues but no valid lines
#         # --------------------------------------------------

#         if not valid_issues:
#             await complete_ai_review_check(
#                 installation_id=installation_id,
#                 owner=owner,
#                 repo=repo,
#                 check_run_id=check_run_id,
#                 issues_count=len(issues),
#             )

#             print(
#                 "Gemini returned issues, but none "
#                 "had valid file/line information."
#             )

#             return {
#                 "status": "completed",
#                 "issues": len(issues),
#                 "inline_comments": 0,
#             }

#         # --------------------------------------------------
#         # 7. Create GitHub inline review
#         # --------------------------------------------------

#         github_review = (
#             await create_pull_request_review(
#                 installation_id=installation_id,
#                 owner=owner,
#                 repo=repo,
#                 pull_number=pull_number,
#                 commit_id=commit_id,
#                 issues=valid_issues,
#             )
#         )

#         print("=" * 60)
#         print(
#             f"GitHub review created for "
#             f"PR #{pull_number}"
#         )
#         print(
#             f"Review URL: "
#             f"{github_review.get('html_url')}"
#         )
#         print("=" * 60)

#         # --------------------------------------------------
#         # 8. Mark Check Run as completed
#         # --------------------------------------------------

#         await complete_ai_review_check(
#             installation_id=installation_id,
#             owner=owner,
#             repo=repo,
#             check_run_id=check_run_id,
#             issues_count=len(valid_issues),
#         )

#         print(
#             f"AI review check completed for "
#             f"PR #{pull_number}"
#         )

#         return {
#             "status": "completed",
#             "issues": len(issues),
#             "inline_comments": len(valid_issues),
#             "review_url": github_review.get(
#                 "html_url"
#             ),
#         }

#     except Exception as exc:
#         # --------------------------------------------------
#         # 9. Mark Check Run as failed
#         # --------------------------------------------------

#         print("=" * 60)
#         print("AI REVIEW FAILED")
#         print(str(exc))
#         print("=" * 60)

#         try:
#             await complete_ai_review_check(
#                 installation_id=installation_id,
#                 owner=owner,
#                 repo=repo,
#                 check_run_id=check_run_id,
#                 issues_count=0,
#             )
#         except Exception as check_error:
#             print(
#                 "Failed to update GitHub Check Run:"
#             )
#             print(str(check_error))

#         raise


# @app.post("/webhooks/github")
# async def github_webhook(request: Request):
#     payload = await request.json()

#     event_type = request.headers.get(
#         "X-GitHub-Event"
#     )

#     print("=" * 60)
#     print("GitHub webhook received")
#     print(f"Event: {event_type}")
#     print("=" * 60)

#     if event_type != "pull_request":
#         print(
#             f"Ignoring event: {event_type}"
#         )

#         return {
#             "status": "ignored",
#             "event": event_type,
#         }

#     action = payload.get("action")

#     print(
#         f"Pull request action: {action}"
#     )

#     if action not in {
#         "opened",
#         "synchronize",
#         "reopened",
#     }:
#         print(
#             f"Ignoring pull request action: "
#             f"{action}"
#         )

#         return {
#             "status": "ignored",
#             "action": action,
#         }

#     pull_request = payload.get(
#         "pull_request",
#         {}
#     )

#     repository = payload.get(
#         "repository",
#         {}
#     )

#     installation = payload.get(
#         "installation",
#         {}
#     )

#     installation_id = installation.get(
#         "id"
#     )

#     pull_number = pull_request.get(
#         "number"
#     )

#     commit_id = (
#         pull_request
#         .get("head", {})
#         .get("sha")
#     )

#     owner = (
#         repository
#         .get("owner", {})
#         .get("login")
#     )

#     repo = repository.get(
#         "name"
#     )

#     print(
#         f"Repository: {owner}/{repo}"
#     )

#     print(
#         f"PR number: #{pull_number}"
#     )

#     print(
#         f"PR title: "
#         f"{pull_request.get('title')}"
#     )

#     print(
#         f"Installation ID: "
#         f"{installation_id}"
#     )

#     print(
#         f"Commit: {commit_id}"
#     )

#     if not installation_id:
#         return {
#             "status": "error",
#             "message": (
#                 "Missing GitHub installation ID"
#             ),
#         }

#     if not pull_number:
#         return {
#             "status": "error",
#             "message": (
#                 "Missing pull request number"
#             ),
#         }

#     if not commit_id:
#         return {
#             "status": "error",
#             "message": (
#                 "Missing pull request commit SHA"
#             ),
#         }

#     if not owner or not repo:
#         return {
#             "status": "error",
#             "message": (
#                 "Missing repository information"
#             ),
#         }

#     try:
#         result = await review_pull_request(
#             installation_id=installation_id,
#             owner=owner,
#             repo=repo,
#             pull_number=pull_number,
#             commit_id=commit_id,
#         )

#         return {
#             "status": "reviewed",
#             "pull_request": pull_number,
#             "result": result,
#         }

#     except Exception as exc:
#         print("=" * 60)
#         print("WEBHOOK REVIEW ERROR")
#         print(str(exc))
#         print("=" * 60)

#         return {
#             "status": "error",
#             "pull_request": pull_number,
#             "message": str(exc),
#         }


import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request

from app.github import (
    complete_ai_review_check,
    create_ai_review_check,
    create_pull_request_review,
    get_pull_request_files,
)
from app.reviewer import review_files
from app.review_state import (
    filter_new_issues,
    mark_missing_issues_inactive,
    save_active_issues,
)


load_dotenv()


app = FastAPI(
    title="PR Review Agent",
    description="AI-powered GitHub Pull Request reviewer",
    version="0.1.0",
)


@app.get("/")
async def root():
    return {
        "message": "PR Review Agent is running"
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }


async def review_pull_request(
    installation_id: int,
    owner: str,
    repo: str,
    pull_number: int,
    commit_id: str,
):
    print("=" * 60)
    print(
        f"Starting AI review for PR #{pull_number}"
    )
    print(
        f"Repository: {owner}/{repo}"
    )
    print(
        f"Commit: {commit_id}"
    )
    print("=" * 60)

    # --------------------------------------------------
    # 1. Create GitHub Check Run
    # --------------------------------------------------

    check_run_id = await create_ai_review_check(
        installation_id=installation_id,
        owner=owner,
        repo=repo,
        commit_id=commit_id,
    )

    print(
        f"AI review check created: "
        f"{check_run_id}"
    )

    try:
        # --------------------------------------------------
        # 2. Get changed files
        # --------------------------------------------------

        files = await get_pull_request_files(
            installation_id=installation_id,
            owner=owner,
            repo=repo,
            pull_number=pull_number,
        )

        print(
            f"Changed files: {len(files)}"
        )

        # --------------------------------------------------
        # 3. Run Gemini review
        # --------------------------------------------------

        review = await review_files(files)

        issues = review.get(
            "issues",
            []
        )

        print(
            f"Gemini found {len(issues)} issue(s)"
        )

        # --------------------------------------------------
        # 4. Mark issues that disappeared as inactive
        # --------------------------------------------------
        #
        # Example:
        #
        # Commit 1:
        #   hardcoded API key -> active
        #
        # Commit 2:
        #   API key removed -> Gemini doesn't report it
        #
        # PostgreSQL marks the old issue inactive.
        #

        await mark_missing_issues_inactive(
            repository=f"{owner}/{repo}",
            pull_number=pull_number,
            current_issues=issues,
        )

        # --------------------------------------------------
        # 5. No issues found
        # --------------------------------------------------

        if not issues:
            await complete_ai_review_check(
                installation_id=installation_id,
                owner=owner,
                repo=repo,
                check_run_id=check_run_id,
                issues_count=0,
            )

            print(
                f"No issues found for PR "
                f"#{pull_number}"
            )

            return {
                "status": "completed",
                "issues": 0,
                "new_issues": 0,
                "inline_comments": 0,
            }

        # --------------------------------------------------
        # 6. Validate Gemini issues
        # --------------------------------------------------

        valid_issues = []

        for issue in issues:
            file = issue.get(
                "file"
            )

            line = issue.get(
                "line"
            )

            if not file:
                print(
                    "Skipping issue without file"
                )

                continue

            if not isinstance(
                line,
                int,
            ):
                print(
                    "Skipping issue without "
                    f"valid line: {issue}"
                )

                continue

            valid_issues.append(
                issue
            )

        # --------------------------------------------------
        # 7. If Gemini returned issues but none
        #    have valid file/line information
        # --------------------------------------------------

        if not valid_issues:
            await complete_ai_review_check(
                installation_id=installation_id,
                owner=owner,
                repo=repo,
                check_run_id=check_run_id,
                issues_count=len(issues),
            )

            print(
                "Gemini returned issues, but none "
                "had valid file/line information."
            )

            return {
                "status": "completed",
                "issues": len(issues),
                "new_issues": 0,
                "inline_comments": 0,
            }

        # --------------------------------------------------
        # 8. IMPORTANT:
        #    Find NEW issues BEFORE saving them.
        #
        #    If we saved first, every issue would look
        #    like an existing issue.
        # --------------------------------------------------

        new_issues = await filter_new_issues(
            repository=f"{owner}/{repo}",
            pull_number=pull_number,
            issues=valid_issues,
        )

        print(
            f"New issues: "
            f"{len(new_issues)}"
        )

        existing_issue_count = (
            len(valid_issues)
            - len(new_issues)
        )

        print(
            f"Existing issues skipped: "
            f"{existing_issue_count}"
        )

        # --------------------------------------------------
        # 9. Save CURRENT review state
        # --------------------------------------------------
        #
        # This happens AFTER filtering.
        #
        # The database now knows which issues are
        # currently active for this PR.
        #

        await save_active_issues(
            repository=f"{owner}/{repo}",
            pull_number=pull_number,
            issues=valid_issues,
        )

        # --------------------------------------------------
        # 10. Create GitHub comments ONLY for NEW issues
        # --------------------------------------------------

        github_review = None

        if new_issues:
            github_review = (
                await create_pull_request_review(
                    installation_id=installation_id,
                    owner=owner,
                    repo=repo,
                    pull_number=pull_number,
                    commit_id=commit_id,
                    issues=new_issues,
                )
            )

            print("=" * 60)
            print(
                f"GitHub review created for "
                f"PR #{pull_number}"
            )

            print(
                f"New inline comments: "
                f"{len(new_issues)}"
            )

            print(
                f"Review URL: "
                f"{github_review.get('html_url')}"
            )

            print("=" * 60)

        else:
            print(
                "No new issues."
            )

            print(
                "Skipping GitHub review comment."
            )

        # --------------------------------------------------
        # 11. Mark Check Run as completed
        # --------------------------------------------------

        await complete_ai_review_check(
            installation_id=installation_id,
            owner=owner,
            repo=repo,
            check_run_id=check_run_id,
            issues_count=len(valid_issues),
        )

        print(
            f"AI review check completed for "
            f"PR #{pull_number}"
        )

        return {
            "status": "completed",
            "issues": len(valid_issues),
            "new_issues": len(new_issues),
            "existing_issues": existing_issue_count,
            "inline_comments": len(new_issues),
            "review_url": (
                github_review.get(
                    "html_url"
                )
                if github_review
                else None
            ),
        }

    except Exception as exc:
        print("=" * 60)
        print("AI REVIEW FAILED")
        print(str(exc))
        print("=" * 60)

        raise


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
):
    payload = await request.json()

    event_type = request.headers.get(
        "X-GitHub-Event"
    )

    print("=" * 60)
    print("GitHub webhook received")
    print(
        f"Event: {event_type}"
    )
    print("=" * 60)

    # --------------------------------------------------
    # 1. Only handle pull_request events
    # --------------------------------------------------

    if event_type != "pull_request":
        print(
            f"Ignoring event: "
            f"{event_type}"
        )

        return {
            "status": "ignored",
            "event": event_type,
        }

    # --------------------------------------------------
    # 2. Get PR action
    # --------------------------------------------------

    action = payload.get(
        "action"
    )

    print(
        f"Pull request action: "
        f"{action}"
    )

    # We review when:
    #
    # opened       -> new PR
    # synchronize  -> new commit pushed
    # reopened     -> PR reopened
    #

    if action not in {
        "opened",
        "synchronize",
        "reopened",
    }:
        print(
            "Ignoring pull request action: "
            f"{action}"
        )

        return {
            "status": "ignored",
            "action": action,
        }

    # --------------------------------------------------
    # 3. Extract GitHub information
    # --------------------------------------------------

    pull_request = payload.get(
        "pull_request",
        {},
    )

    repository = payload.get(
        "repository",
        {},
    )

    installation = payload.get(
        "installation",
        {},
    )

    installation_id = installation.get(
        "id"
    )

    pull_number = pull_request.get(
        "number"
    )

    commit_id = (
        pull_request
        .get("head", {})
        .get("sha")
    )

    owner = (
        repository
        .get("owner", {})
        .get("login")
    )

    repo = repository.get(
        "name"
    )

    print(
        f"Repository: "
        f"{owner}/{repo}"
    )

    print(
        f"PR number: "
        f"#{pull_number}"
    )

    print(
        f"PR title: "
        f"{pull_request.get('title')}"
    )

    print(
        f"Installation ID: "
        f"{installation_id}"
    )

    print(
        f"Commit: "
        f"{commit_id}"
    )

    # --------------------------------------------------
    # 4. Validate webhook data
    # --------------------------------------------------

    if not installation_id:
        return {
            "status": "error",
            "message": (
                "Missing GitHub "
                "installation ID"
            ),
        }

    if not pull_number:
        return {
            "status": "error",
            "message": (
                "Missing pull request "
                "number"
            ),
        }

    if not commit_id:
        return {
            "status": "error",
            "message": (
                "Missing pull request "
                "commit SHA"
            ),
        }

    if not owner or not repo:
        return {
            "status": "error",
            "message": (
                "Missing repository "
                "information"
            ),
        }

    # --------------------------------------------------
    # 5. Start AI review
    # --------------------------------------------------

    try:
        result = await review_pull_request(
            installation_id=installation_id,
            owner=owner,
            repo=repo,
            pull_number=pull_number,
            commit_id=commit_id,
        )

        return {
            "status": "reviewed",
            "pull_request": pull_number,
            "result": result,
        }

    except Exception as exc:
        print("=" * 60)
        print(
            "WEBHOOK REVIEW ERROR"
        )
        print(str(exc))
        print("=" * 60)

        return {
            "status": "error",
            "pull_request": pull_number,
            "message": str(exc),
        }