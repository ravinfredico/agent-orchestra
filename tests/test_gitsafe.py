import subprocess

import pytest

from orchestra.gitsafe import RepoError, prepare_repo


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.py").write_text("x = 1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_not_a_repo(tmp_path):
    with pytest.raises(RepoError, match="not a git repo"):
        prepare_repo(tmp_path)


def test_dirty_repo_refused(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "a.py").write_text("x = 2\n")
    with pytest.raises(RepoError, match="uncommitted"):
        prepare_repo(repo)


def test_clean_repo_gets_branch(tmp_path):
    repo = make_repo(tmp_path)
    branch = prepare_repo(repo)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert head == branch and branch.startswith("orchestra/")
