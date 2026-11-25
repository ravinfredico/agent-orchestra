"""Safety for --repo runs: work on a fresh git branch so nothing touches your main branch."""

import subprocess
import time
from pathlib import Path


class RepoError(Exception):
    pass


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RepoError(r.stderr.strip() or f"git {' '.join(args)} failed")
    return r.stdout.strip()


def check_allowed(repo: Path, root: Path | None) -> None:
    """When REPOS_ROOT is set (required when hosted), only repos inside it may be used."""
    if root is None:
        return
    repo, root = Path(repo).resolve(), Path(root).resolve()
    if repo != root and root not in repo.parents:
        raise RepoError(f"{repo} is outside the allowed folder {root}.")


def prepare_repo(repo: Path, allow_dirty: bool = False, verbose: bool = True) -> str:
    """Check the repo is clean, then switch to a new branch. Returns the branch name."""
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise RepoError(f"{repo} is not a folder")
    try:
        _git(repo, "rev-parse", "--is-inside-work-tree")
    except RepoError:
        raise RepoError(f"{repo} is not a git repo. Run `git init` and commit first, so every "
                        "agent change can be reviewed and undone.")
    if _git(repo, "status", "--porcelain") and not allow_dirty:
        raise RepoError("You have uncommitted changes. Commit or stash them first "
                        "(or pass --allow-dirty), so agent edits don't mix with yours.")
    original = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    branch = f"orchestra/{time.strftime('%Y%m%d-%H%M%S')}"
    _git(repo, "checkout", "-b", branch)
    if verbose:
        print(f"Working on new branch '{branch}' (from '{original}').")
        print(f"Review afterwards with:  git -C {repo} diff {original}...{branch}")
    return branch
