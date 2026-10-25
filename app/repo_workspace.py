import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


CLONE_ROOT = Path(
    os.getenv(
        "REPO_CLONE_ROOT",
        "/Users/meena/Documents/backend/fast_api/clone_repo_for_test",
    )
)

def _safe_name(value: str) -> str:
    return "".join(
        ch if ch.isalnum() or ch in "-_." else "_"
        for ch in value
    )


SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "coverage",
}

MAX_SEARCH_MATCHES = 40
MAX_SEARCH_OUTPUT_CHARS = 12000
MAX_READ_LINES = 400
GIT_TIMEOUT_SECONDS = 120
SEARCH_TIMEOUT_SECONDS = 20


class RepoWorkspace:
    def __init__(
        self,
        owner: str,
        repo: str,
        commit_id: str,
        clone_url: str,
        access_token: str,
        pull_number: Optional[int] = None,
    ):
        self.owner = owner
        self.repo = repo
        self.commit_id = commit_id
        self.clone_url = clone_url
        self.access_token = access_token
        self.pull_number = pull_number
        safe_owner = _safe_name(owner)
        safe_repo = _safe_name(repo)
        self.root = CLONE_ROOT / f"{safe_owner}__{safe_repo}"
        self._fetched = False

    def authenticated_clone_url(self) -> str:
        if self.clone_url.startswith("https://"):
            return self.clone_url.replace(
                "https://",
                f"https://x-access-token:{self.access_token}@",
                1,
            )

        return self.clone_url

    def fetch_repo(self) -> str:
        CLONE_ROOT.mkdir(parents=True, exist_ok=True)

        git_dir = self.root / ".git"
        url = self.authenticated_clone_url()

        try:
            self.root.resolve().relative_to(
                CLONE_ROOT.resolve()
            )
        except ValueError as exc:
            raise RuntimeError(
                "Refusing to use a path outside "
                f"the clone root: {self.root}"
            ) from exc

        if self.root.exists() and not git_dir.exists():
            shutil.rmtree(self.root)

        if not git_dir.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            self._run_git(
                [
                    "git",
                    "init",
                    str(self.root),
                ]
            )
            self._run_git(
                [
                    "git",
                    "-C",
                    str(self.root),
                    "remote",
                    "add",
                    "origin",
                    url,
                ]
            )
        else:
            self._run_git(
                [
                    "git",
                    "-C",
                    str(self.root),
                    "remote",
                    "set-url",
                    "origin",
                    url,
                ]
            )

        try:
            self._run_git(
                [
                    "git",
                    "-C",
                    str(self.root),
                    "fetch",
                    "--depth",
                    "1",
                    "origin",
                    self.commit_id,
                ]
            )
        except RuntimeError:
            if not self.pull_number:
                raise

            self._run_git(
                [
                    "git",
                    "-C",
                    str(self.root),
                    "fetch",
                    "--depth",
                    "1",
                    "origin",
                    f"pull/{self.pull_number}/head",
                ]
            )

        self._run_git(
            [
                "git",
                "-C",
                str(self.root),
                "checkout",
                "--force",
                "FETCH_HEAD",
            ]
        )

        self._fetched = True

        return (
            f"Repository ready at {self.root} "
            f"for commit {self.commit_id}."
        )

    def search_code(
        self,
        query: str,
        path: str = "",
    ) -> str:
        if not self._ensure_fetched():
            return (
                "Repository is not fetched yet. "
                "Call fetch_repo first."
            )

        if not query or not query.strip():
            return "search_code requires a non-empty query."

        search_root = self._safe_path(path) if path else self.root

        if search_root is None:
            return f"Invalid path: {path}"

        rg_path = shutil.which("rg")

        if rg_path:
            result = subprocess.run(
                [
                    rg_path,
                    "-n",
                    "--max-count",
                    "20",
                    "-g",
                    "!**/.git/**",
                    "-g",
                    "!**/node_modules/**",
                    query,
                    str(search_root),
                ],
                capture_output=True,
                text=True,
                timeout=SEARCH_TIMEOUT_SECONDS,
            )
            output = result.stdout.strip()

            if not output:
                return f"No matches for {query!r}."

            return self._trim_search_output(output)

        return self._python_search(query, search_root)

    def read_file(
        self,
        path: str,
        start_line: int = 1,
        end_line: Optional[int] = None,
    ) -> str:
        if not self._ensure_fetched():
            return (
                "Repository is not fetched yet. "
                "Call fetch_repo first."
            )

        file_path = self._safe_path(path)

        if file_path is None:
            return f"Invalid path: {path}"

        if not file_path.is_file():
            return f"File not found: {path}"

        try:
            text = file_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            return f"Could not read {path}: {exc}"

        lines = text.splitlines()
        total = len(lines)

        start = max(int(start_line), 1)

        if end_line is None:
            end = min(start + MAX_READ_LINES - 1, total)
        else:
            end = min(int(end_line), total)

        if end < start:
            return "end_line must be >= start_line."

        if end - start + 1 > MAX_READ_LINES:
            end = start + MAX_READ_LINES - 1

        numbered = []

        for index, line in enumerate(
            lines[start - 1:end],
            start=start,
        ):
            numbered.append(f"{index}: {line}")

        return (
            f"File: {path} (lines {start}-{end} of {total})\n"
            + "\n".join(numbered)
        )

    def _ensure_fetched(self) -> bool:
        if self._fetched:
            return True

        if (self.root / ".git").exists():
            self._fetched = True
            return True

        return False

    def _safe_path(self, relative_path: str) -> Optional[Path]:
        if not relative_path:
            return self.root

        cleaned = relative_path.lstrip("/")
        candidate = (self.root / cleaned).resolve()

        try:
            candidate.relative_to(self.root.resolve())
        except ValueError:
            return None

        return candidate

    def _run_git(self, command: list[str]) -> str:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = "echo"

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            env=env,
        )

        if result.returncode != 0:
            stderr = self._redact(result.stderr.strip())
            stdout = self._redact(result.stdout.strip())
            raise RuntimeError(
                "Git command failed: "
                f"{stdout} {stderr}".strip()
            )

        return result.stdout.strip()

    def _redact(self, text: str) -> str:
        if self.access_token:
            return text.replace(self.access_token, "***")

        return text

    def _trim_search_output(self, output: str) -> str:
        lines = output.splitlines()
        trimmed = lines[:MAX_SEARCH_MATCHES]
        text = "\n".join(trimmed)

        if len(text) > MAX_SEARCH_OUTPUT_CHARS:
            text = text[:MAX_SEARCH_OUTPUT_CHARS] + "\n...truncated..."

        if len(lines) > MAX_SEARCH_MATCHES:
            text += (
                f"\n... {len(lines) - MAX_SEARCH_MATCHES} "
                "more matches omitted."
            )

        return text

    def _python_search(
        self,
        query: str,
        search_root: Path,
    ) -> str:
        matches = []

        for dirpath, dirnames, filenames in os.walk(search_root):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in SKIP_DIR_NAMES
            ]

            for filename in filenames:
                file_path = Path(dirpath) / filename

                try:
                    content = file_path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                except OSError:
                    continue

                rel = file_path.relative_to(self.root)

                for line_number, line in enumerate(
                    content.splitlines(),
                    start=1,
                ):
                    if query in line:
                        matches.append(
                            f"{rel}:{line_number}:{line}"
                        )

                        if len(matches) >= MAX_SEARCH_MATCHES:
                            return self._trim_search_output(
                                "\n".join(matches)
                            )

        if not matches:
            return f"No matches for {query!r}."

        return self._trim_search_output("\n".join(matches))
