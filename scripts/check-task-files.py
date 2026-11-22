#!/usr/bin/env python3
"""worktree에서 ship하기 전 검사. 주 폴더에서는 언제나 통과한다.

jk-git ship은 저장소에 이 파일이 있으면 1번(touched_task_files)을 직접 부르고, 2번은 자기 fetch 뒤의
기본 브랜치 검사로 대신한다. ship 밖에서는 `python3 scripts/check-task-files.py`로 둘 다 돌린다.

1. 이 브랜치가 TASKS.md, STATE.md, LANDED.md를 고쳤으면 실패한다. 할 일 파일은 주 폴더에서만
   고친다(scripts/tasks.py sync). 갈라진 지점(merge-base)부터 작업 트리까지 보므로 main이 앞서간
   변경은 세지 않는다.
2. 아직 푸시하지 않은 브랜치가 최신 origin/main 위에 있지 않으면 실패한다. 푸시하기 전에는
   rebase해도 강제 푸시가 필요 없으므로, 다른 worktree가 먼저 머지한 변경과의 충돌을 여기서 푼다.
   이미 푸시한 브랜치는 rebase하면 강제 푸시가 필요해 이 검사를 건너뛴다.
"""
from pathlib import Path
import subprocess
import sys

TASK_FILES = {"TASKS.md", "STATE.md", "LANDED.md"}


def git(*args, cwd=None):
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return done.stdout.strip() if done.returncode == 0 else None


def ok(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True).returncode == 0


def in_linked_worktree(cwd=None):
    own = git("rev-parse", "--path-format=absolute", "--git-dir", cwd=cwd)
    shared = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)
    return bool(own and shared and Path(own).resolve() != Path(shared).resolve())


def base_ref(cwd=None):
    head = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=cwd)
    for ref in (head, "origin/main", "origin/master", "main", "master"):
        if ref and git("rev-parse", "--verify", "--quiet", ref, cwd=cwd):
            return ref
    return None


def touched_task_files(cwd=None):
    """Return the task files this worktree branch changed, or [] in the main folder."""
    if not in_linked_worktree(cwd):
        return []
    ref = base_ref(cwd)
    base = git("merge-base", ref, "HEAD", cwd=cwd) if ref else None
    if not base:
        raise SystemExit("기준 브랜치를 찾지 못해 할 일 파일 변경을 확인하지 못함")
    changed = (git("diff", "--name-only", base, cwd=cwd) or "").splitlines()
    return sorted(path for path in changed if path in TASK_FILES)


def behind_before_push(cwd=None, fetch=True):
    """Return the base ref when an unpushed worktree branch is not on top of it, else None."""
    if not in_linked_worktree(cwd):
        return None
    if fetch:
        ok("fetch", "--quiet", "origin", cwd=cwd)
    branch = git("branch", "--show-current", cwd=cwd)
    if not branch or git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}", cwd=cwd):
        return None
    ref = base_ref(cwd)
    if ref and not ok("merge-base", "--is-ancestor", ref, "HEAD", cwd=cwd):
        return ref
    return None


def main():
    touched = touched_task_files()
    if touched:
        print("worktree에서 할 일 파일을 고쳤다: " + ", ".join(touched))
        print("되돌리고, 할 일은 scripts/tasks.py로 이슈에 남긴다. 사본은 주 폴더의 sync가 쓴다.")
        sys.exit(1)
    behind = behind_before_push()
    if behind:
        print(f"아직 푸시하지 않은 이 브랜치가 최신 {behind} 위에 있지 않다.")
        print(f"작업을 커밋한 뒤 `git rebase {behind}`로 올리고(충돌이 나면 두 쪽을 모두 살려 푼다) 다시 ship한다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
