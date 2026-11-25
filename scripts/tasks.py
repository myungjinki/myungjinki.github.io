#!/usr/bin/env python3
"""일회성 할 일을 GitHub Issues에 두고, 파일에는 사본만 둔다.

쓰기(이슈에만 쓴다): add, edit, claim, note, turn, release, close, cancel, reopen, fail, fixed
읽기: show(이슈를 표로 보인다. 번호를 주면 할 일 전체), hook(세션 시작 출력: 제목·메타 요약표와 알릴 것만)
사본: sync(주 폴더에서 TASKS.md '일회성' 표, STATE.md '진행 중' 표, LANDED.md를 이슈에 맞춘다)

끝내는 순서: PR 본문의 `Closes #n`이 머지할 때 이슈를 먼저 닫고, 그 뒤 `close`가 닫힌 이슈에 `끝:` 댓글을 단다.
그 사이에 sync가 돌면 LANDED.md에 `(요약 없음, 이슈 #n)` 행이 들어가지만, 다음 sync가 댓글을 읽어 그 행을
고치고 `--now`를 다시 보인다. sync는 주 폴더가 기본 브랜치에 있고 origin보다 뒤처지지 않았을 때만 쓴다.

설정은 대상 저장소의 scripts/tasks.json에 둔다. ticker가 없으면 새 방식, 있으면 옛 방식이다.
- 새 방식({"since": "YYYY-MM-DD"}, since는 생략 가능): 번호는 이슈 번호다. 저장소 안에서는 `#173`, 다른 저장소에서는 `저장소#173`으로
  적고 이슈 제목에는 붙이지 않는다. 명령은 `173`·`"#173"`·`"저장소#173"`을 받고, 다른 저장소의 번호와 PR 번호는 거부한다.
  sync는 KST로 since 당일부터 닫힌 이슈만 LANDED.md에 적는다(since가 없으면 모두).
- 옛 방식({"ticker": "RAE", "offset": n}): 새 번호는 이슈 번호 + offset이고 sync가 제목 앞에 `RAE-n`을 붙인다.
이슈 본문은 할 일 설명 뒤에 `순서: n`·`대기: 조건` 줄을 둔다. 라벨은 `구분:`·`등급:`·`차례:`·`목표:`, `진행중`, `막을 것`이다.
목표는 `목표:G2` 라벨이고 부모는 GitHub 하위 이슈다. 자기 라벨이 없으면 부모를 8단계까지 따라 올라가 물려받는다.
`G0`·`G1`은 혼자만 쓰고 라벨이 없는 것은 미정이다. 규칙은 사내 지침의 docs/01-goals.md를 따른다.
댓글의 첫 줄로 상태를 남긴다: `잡음: 이름`, `놓음: 이름`, `메모: 이름`, `끝: 모델`, `취소: 이름`, `다시 엶: 이름`,
`실패: 이름`, `막음: 이름`. `claim`은 댓글에 브랜치·워크트리·시각을 남기고 워크트리별 `.git/tasks-session.json`에
세션 이름과 잡은 일을 저장해 같은 워크트리에서 무인자 `note`·`release`가 동작하게 한다. 24시간 이상 갱신 없는
선점은 `hook`·`show`·`sync`와 `claim` 충돌 안내에서 경고한다.

할 일 이슈는 `구분:`·`등급:`·`차례:` 라벨이 하나라도 있는 이슈다(옛 방식은 제목이 `<티커>-n`으로 시작하는 이슈도). 그 밖의 이슈(버그 신고 등)는
표·LANDED에 넣지 않고 제목도 바꾸지 않는다. 할 일로 삼으려면 `turn "#이슈번호" AI`로 차례 라벨을 단다.

GitHub 웹·휴대폰에서 `.github/ISSUE_TEMPLATE/task.yml` 양식으로 만든 이슈는 `### 할 일` 같은 칸 제목으로 본문이 온다.
`show`·`hook`은 그 칸을 읽어 보이고, `sync`는 본문을 `순서:`·`대기:` 줄 형식으로, 고른 칸을 `구분:`·`등급:`·`차례:`·`목표:` 라벨로 바꾼다.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import re
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
# Increase when a changed tasks.py should replace older repository copies.
TASKS_SCRIPT_VERSION = 6
KST = timezone(timedelta(hours=9))
ACTIVE = "진행중"
FAILED = "막을 것"
TURNS = ("AI", "사용자", "대기")
GRADES = ("최상", "상", "중", "하", "-")
FIELDS = "number,title,body,labels,comments,state,closedAt,url"
BRIEF = "number,title,labels,state,closedAt,url"
TASK_LABELS = ("구분", "등급", "차례")
GOALS = tuple(f"G{n}" for n in range(9))
SOLO_GOALS = ("G0", "G1")
UNDECIDED = "미정"
PARENT_LEVELS = 8
PARENT_URL = re.compile(r"https://github\.com/([\w.-]+)/([\w.-]+)/issues/([1-9]\d*)")
ISSUE_URL = re.compile(r"https://[^/]+/[\w.-]+/([\w.-]+)/(issues|pull)/[1-9]\d*")
# 새 방식의 번호: 173, #173, 저장소#173
REF = re.compile(r"(?:([\w.-]+)?#)?([1-9]\d*)")
REOPENED = "다시 엶"
META = re.compile(r"^(순서|대기):\s*(.*)$")
NOTICE = "이 표는 GitHub Issues의 사본이다. 고치지 말고 scripts/tasks.py를 쓴다."
# 이슈 양식(.github/ISSUE_TEMPLATE/task.yml)의 칸 제목 → 본문 메타나 라벨 이름
FORM_FIELDS = {"할 일": "text", "구분": "구분", "등급": "등급", "차례": "차례", "순서": "순서", "대기 조건": "대기",
               "목표": "목표"}
NO_RESPONSE = "_No response_"
LABEL_COLORS = {"차례": "1d76db", "등급": "5319e7", "구분": "0e8a16", "목표": "fbca04", ACTIVE: "d93f0b", FAILED: "b60205"}
STALE_HOURS = 24
CACHE_TTL_SECONDS = 180


def parent_fields(levels):
    nested = ""
    for _ in range(levels):
        nested = "parent { number title url repository { nameWithOwner } labels(first:100) { nodes { name } } %s }" % nested
    return nested


PARENT_FIELDS = parent_fields(PARENT_LEVELS)
ISSUE_FIELDS = """
    number title body state closedAt url
    labels(first:100) { nodes { name } pageInfo { hasNextPage } }
    comments(last:100) { nodes { body createdAt url } pageInfo { hasPreviousPage } }
    %s
""" % PARENT_FIELDS
OPEN_AND_FAILED = """
query($owner:String!, $name:String!) {
    repository(owner:$owner, name:$name) {
        opened:issues(states:OPEN, first:100) { nodes { ...TaskIssue } pageInfo { hasNextPage } }
        failed:issues(filterBy:{labels:["막을 것"]}, first:100) { nodes { ...TaskIssue } pageInfo { hasNextPage } }
    }
}
fragment TaskIssue on Issue { %s }
""" % ISSUE_FIELDS


NODE = """
query($owner:String!, $name:String!, $number:Int!) {
    repository(owner:$owner, name:$name) { issue(number:$number) { id url parent { id } } }
}
"""
ADD_PARENT = """
mutation($parent:ID!, $child:String!) {
    addSubIssue(input:{issueId:$parent, subIssueUrl:$child, replaceParent:true}) { subIssue { number } }
}
"""
DROP_PARENT = """
mutation($parent:ID!, $child:ID!) {
    removeSubIssue(input:{issueId:$parent, subIssueId:$child}) { subIssue { number } }
}
"""


class GhError(Exception):
    def __init__(self, message="", stdout=""):
        super().__init__(message)
        self.stdout = stdout


# ---------- 순수 함수: 테스트 대상 ----------

def load_config(path):
    """Return (ticker, offset). Without a ticker the issue number is the task number: (None, 0)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "ticker" not in data:
        return None, 0
    return data["ticker"], int(data["offset"])


def load_since(path):
    """Return the first KST day whose closed issues go into LANDED.md, or None for all of them."""
    try:
        since = json.loads(Path(path).read_text(encoding="utf-8")).get("since")
    except FileNotFoundError:
        return None
    return None if since is None else valid_day(since)


def valid_day(text):
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text).isoformat()
    except (TypeError, ValueError):
        pass
    raise SystemExit(f"since는 YYYY-MM-DD 날짜다: {text}")


def task_id(issue, ticker, offset):
    """The id shown for an issue: `#n`, or the old `<ticker>-n`."""
    if ticker is None:
        return f"#{issue['number']}"
    return ticker_of(issue.get("title"), ticker)[0] or f"{ticker}-{issue['number'] + offset}"


def typed(tid):
    """An id as it is typed in a shell, where a leading `#` would start a comment."""
    return tid.lstrip("#")


def parse_ref(ref):
    """Split `173`, `#173` or `저장소#173` into (repository or None, number)."""
    match = REF.fullmatch(ref.strip())
    if not match:
        raise SystemExit(f"{ref}: 이 저장소의 할 일 번호는 이슈 번호다. 173, \"#173\", \"저장소#173\" 가운데 하나로 준다")
    return match.group(1), int(match.group(2))


def number_here(ref, repository):
    """The issue number in ref. repository() names this repository and is asked only when ref names one."""
    repo, number = parse_ref(ref)
    if repo:
        here = repository()
        if repo.lower() != here.lower():
            raise SystemExit(f"{ref.strip()}은 이 저장소({here or '이름 확인 못 함'})의 할 일이 아니라 아무것도 하지 않았다")
    return number


def repo_of(issue):
    """The repository name in an issue's URL, or of a GraphQL parent."""
    match = ISSUE_URL.match(issue.get("url") or "")
    return match.group(1) if match else (issue.get("repository") or {}).get("nameWithOwner", "").rsplit("/", 1)[-1]


def is_pull(issue):
    match = ISSUE_URL.match(issue.get("url") or "")
    return bool(match) and match.group(2) == "pull"


def ticker_of(title, ticker):
    """Split an issue title into (ticker id or None, rest)."""
    if ticker is None:
        return None, (title or "").strip()
    match = re.match(rf"^({re.escape(ticker)}-\d+)\b\s*(.*)$", (title or "").strip())
    return (match.group(1), match.group(2).strip()) if match else (None, (title or "").strip())


def parse_body(body):
    """Split an issue body into (text, meta) where meta holds the trailing 순서·대기 lines."""
    lines = (body or "").replace("\r\n", "\n").rstrip().split("\n")
    meta = {}
    while lines and (not lines[-1].strip() or META.match(lines[-1].strip())):
        line = lines.pop().strip()
        if line:
            key, value = META.match(line).groups()
            meta.setdefault(key, value.strip())
    return "\n".join(lines).strip(), meta


def make_body(text, meta):
    tail = [f"{key}: {meta[key]}" for key in ("순서", "대기") if meta.get(key) not in (None, "")]
    return text.strip() + ("\n\n" + "\n".join(tail) if tail else "") + "\n"


def parse_form(body):
    """Read the fields of an issue made from the task form, or None for any other body."""
    parts = re.split(r"(?m)^### (.+?)[ \t]*$", (body or "").replace("\r\n", "\n"))
    if len(parts) < 3 or parts[0].strip() or parts[1] != "할 일":
        return None
    fields = {}
    for name, value in zip(parts[1::2], parts[2::2]):
        value = value.strip()
        if name in FORM_FIELDS and value and value != NO_RESPONSE:
            fields[FORM_FIELDS[name]] = value
    return fields


def form_fix(issue):
    """Return (body, add, drop) that turn a task-form issue into the usual body and labels, or None."""
    form = parse_form(issue.get("body"))
    if form is None:
        return None
    valid = {"구분": lambda v: True, "등급": lambda v: v in GRADES[:4], "차례": lambda v: v in TURNS}
    add = [f"{key}:{form[key]}" for key in TASK_LABELS if key in form and valid[key](form[key])]
    try:
        add += goal_labels(parse_goals(form["목표"])) if "목표" in form else []
    except ValueError:
        pass  # sync가 잘못된 값을 알린다
    prefixes = {name.split(":", 1)[0] for name in add}
    drop = [n for n in label_names(issue) if n.split(":", 1)[0] in prefixes and n not in add]
    body = make_body(form.get("text", ""), {key: form.get(key) for key in ("순서", "대기")})
    return body, add, drop


def label_names(issue):
    labels = issue.get("labels") or []
    if isinstance(labels, dict):  # 부모는 GraphQL 응답 그대로다
        labels = labels["nodes"]
    return [label["name"] if isinstance(label, dict) else label for label in labels]


def parse_goals(text):
    """Return goal numbers from "G2,G4", or [] for 미정. Raises ValueError for anything the handbook forbids."""
    names = [name.strip() for name in text.split(",")]
    if names == [UNDECIDED]:
        return []
    wrong = [name for name in names if name not in GOALS]
    if wrong:
        raise ValueError(f"목표는 G0–G8(쉼표로 여럿)이나 미정이다: {', '.join(wrong) or text}")
    names = sorted(set(names))
    if len(names) > 1 and set(names) & set(SOLO_GOALS):
        raise ValueError(f"G0과 G1은 혼자만 쓴다: {','.join(names)}")
    return names


def goal_labels(goals):
    return [f"목표:{goal}" for goal in goals]


def label_goals(issue):
    """Goals from the issue's own labels."""
    found = {name.split(":", 1)[1] for name in label_names(issue) if name.startswith("목표:")}
    return [goal for goal in GOALS if goal in found]


def own_goals(issue):
    """Goals set on the issue itself: its labels, or the form field sync has not turned into labels yet."""
    goals = label_goals(issue)
    if goals:
        return goals
    try:
        return parse_goals((parse_form(issue.get("body")) or {}).get("목표", UNDECIDED))
    except ValueError:
        return []


def needs_effect(issue):
    """Goals that make closing require a 전 → 후 line: the issue's own G1–G8 labels. ship asks this before merging."""
    return [goal for goal in label_goals(issue) if goal != "G0"]


def goals_of(issue):
    """Return (goals, chain): the nearest goals up the parents, and the issues passed on the way, the issue first."""
    chain = [issue]
    while True:
        goals = own_goals(chain[-1])
        parent = chain[-1].get("parent")
        if goals or not parent or parent.get("hidden") or len(chain) > PARENT_LEVELS:
            return goals, chain
        chain.append(parent)


def goal_cell(issue):
    return "·".join(goals_of(issue)[0]) or "-"


def goal_known(issue):
    """False when the parents were not read, so a missing label does not mean 미정."""
    return "parent" in issue or bool(own_goals(issue))


def reference(issue, numbered=False):
    """A link to an issue named `저장소#n`; in old-style repositories by its ticker id, or by repository and number."""
    match = re.match(r"[A-Z]+-\d+\b", issue.get("title") or "")
    if numbered:
        name = f"{repo_of(issue)}#{issue['number']}"
    else:
        name = match.group(0) if match else f"{(issue.get('repository') or {}).get('nameWithOwner', '')}#{issue['number']}"
    return f"[{name}]({issue['url']})" if issue.get("url") else name


def goal_path(issue, numbered=False):
    """The way from the goal to this issue, e.g. `G2 ← [chief#1](…) ← [role#5](…)`."""
    if not goal_known(issue):
        return "확인 못 함 (부모를 읽지 못함)"
    goals, chain = goals_of(issue)
    path = " ← ".join(["·".join(goals) or UNDECIDED] + [reference(node, numbered) for node in reversed(chain)])
    parent = chain[-1].get("parent")
    if parent:
        hidden = parent.get("hidden")
        path += " (읽을 수 없는 부모가 있음)" if hidden else f" (부모: {reference(parent, numbered)})" if len(chain) == 1 else ""
    return path


def readable_part(text):
    """Return a GraphQL answer whose only errors are unreadable parents, marked hidden; raise ValueError otherwise."""
    answer = json.loads(text)
    errors = answer.get("errors") or []
    if not answer.get("data") or any("parent" not in (error.get("path") or ()) for error in errors):
        raise ValueError("읽지 못한 응답")
    for error in errors:
        node = answer["data"]
        for key in error["path"]:
            if key == "parent" and node[key] is None:
                node[key] = {"hidden": True}
            if not isinstance(node[key], (dict, list)):
                break
            node = node[key]
            if node == {"hidden": True}:
                break
    return answer


def is_task(issue, ticker):
    """True for issues tasks.py manages: any 구분·등급·차례 label, or a ticker title in old-style repositories."""
    if ticker_of(issue.get("title"), ticker)[0]:
        return True
    return any(name.split(":", 1)[0] in TASK_LABELS for name in label_names(issue) if ":" in name)


def label_value(names, prefix):
    for name in names:
        if name.startswith(prefix + ":"):
            return name.split(":", 1)[1]
    return None


def comment_key(comment):
    match = re.search(r"(\d+)$", comment.get("url") or "")
    return comment.get("createdAt") or "", int(match.group(1)) if match else 0


def head_of(comment):
    """Return (keyword, value) from a comment's first line, e.g. ('잡음', 'name')."""
    first = (comment.get("body") or "").strip().replace("\r\n", "\n").split("\n", 1)[0].strip()
    if ":" not in first:
        return first, ""
    keyword, value = first.split(":", 1)
    return keyword.strip(), value.strip()


def fields_of(comment):
    """Read `key: value` lines after the first line of a comment."""
    found = {}
    for line in (comment.get("body") or "").replace("\r\n", "\n").split("\n")[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            found.setdefault(key.strip(), value.strip())
    return found


def parse_time(stamp):
    """Parse an ISO timestamp string to an aware datetime, or None."""
    if not stamp:
        return None
    try:
        dt = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=KST)


def claim_info(comments):
    """Return current claim details: holder, branch, worktree, claimed_at, activity_at, note.

    The holder is the earliest 잡음 since the last 놓음·끝·취소, so when two sessions
    claim at once every reader picks the same winner. Notes reset with the holder.
    """
    holder, meta, claimed_at, activity_at, note = None, {}, "", "", {}
    for comment in sorted(comments or [], key=comment_key):
        keyword, value = head_of(comment)
        if keyword in ("놓음", "끝", "취소"):
            holder, meta, claimed_at, activity_at, note = None, {}, "", "", {}
        elif keyword == "잡음" and holder is None:
            holder = value
            meta = fields_of(comment)
            claimed_at = meta.get("시각") or comment.get("createdAt") or ""
            activity_at = claimed_at
        elif keyword == "메모":
            note = fields_of(comment)
            if holder is not None and comment.get("createdAt"):
                activity_at = comment["createdAt"]
    return {
        "holder": holder,
        "branch": meta.get("브랜치", ""),
        "worktree": meta.get("워크트리", ""),
        "claimed_at": claimed_at,
        "activity_at": activity_at,
        "note": note,
    }


def claim_state(comments):
    """Return (holder, note fields) from comments."""
    info = claim_info(comments)
    return info["holder"], info["note"]


def claim_age_hours(info, now=None):
    """Hours elapsed since the last activity on an active claim, or None."""
    if not info or not info.get("holder"):
        return None
    when = parse_time(info.get("activity_at") or info.get("claimed_at"))
    if when is None:
        return None
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    return (current - when).total_seconds() / 3600


def stale_claim_lines(items, now=None, hours=STALE_HOURS):
    """Warning lines for active claims older than `hours` without recent activity."""
    lines = []
    for item in sort_items(items):
        age = claim_age_hours(item, now=now)
        if age is None or age < hours:
            continue
        where = f", 브랜치 {item['branch']}" if item.get("branch") else ""
        lines.append(
            f"- {item['id']} ({item['holder']}, {int(age)}시간 전{where}) — "
            f"멈춘 세션이면 `tasks.py release {typed(item['id'])} --force`로 놓는다"
        )
    return lines


def open_failures(comments):
    """Return [(who, what)] for 실패 comments after the last 막음 on one issue."""
    found = []
    for comment in sorted(comments or [], key=comment_key):
        keyword, value = head_of(comment)
        if keyword == "막음":
            found = []
        elif keyword == "실패":
            found.append((value, fields_of(comment).get("무엇") or "내용 미기록"))
    return found


def failure_lines(issues, ticker, offset):
    """Lines for failures not yet blocked, oldest issue first."""
    lines = []
    for issue in sorted(issues or [], key=lambda i: i["number"]):
        tid = task_id(issue, ticker, offset)
        lines += [f"- {tid}: {cell(what)} ({who})" for who, what in open_failures(issue.get("comments"))]
    return lines


def item_of(issue, ticker, offset):
    title = ticker_of(issue.get("title"), ticker)[1]
    names = label_names(issue)
    form = parse_form(issue.get("body"))
    text, meta = (form.get("text", ""), form) if form is not None else parse_body(issue.get("body"))
    turn = label_value(names, "차례") or "미정"
    if turn == "대기":
        turn = "대기: " + (meta.get("대기") or "조건 미기록")
    grade = "-" if turn == "사용자" else (label_value(names, "등급") or "-")
    info = claim_info(issue.get("comments"))
    holder, note = info["holder"], info["note"]
    order = meta.get("순서", "")
    return {
        "number": issue["number"],
        "issue_link": issue_link(issue),
        "id": task_id(issue, ticker, offset),
        "title": title,
        "text": text or title,
        "kind": label_value(names, "구분") or "-",
        "grade": grade,
        "turn": turn,
        "goal": goal_cell(issue),
        "unlinked": "parent" in issue and not issue["parent"] and not own_goals(issue),
        "order": int(order) if order.isdigit() else None,
        "active": ACTIVE in names or holder is not None,
        "holder": holder,
        "branch": info["branch"],
        "worktree": info["worktree"],
        "claimed_at": info["claimed_at"],
        "activity_at": info["activity_at"],
        "stopped": note.get("멈춘 곳") or (f"막 잡음 ({holder})" if holder else "-"),
        "next": note.get("다음 걸음") or "-",
    }


def id_number(tid):
    return int(re.search(r"\d+$", tid).group())


def sort_items(items):
    return sorted(items, key=lambda i: (i["order"] is None, i["order"] or 0, id_number(i["id"])))


def cell(text):
    return " ".join((text or "").split()).replace("|", "\\|")


def issue_link(issue):
    url = issue.get("url")
    return f"[#{issue['number']}]({url})" if url else "-"


def tasks_table(items, *, with_issues=False, with_goals=False):
    rows = ["| 번호 | 구분 | 할 일 | 등급 |" + (" 이슈 |" if with_issues else "") + " 차례 |" + (" 목표 |" if with_goals else ""),
            "|---|---|---|---|" + ("---|" if with_issues else "") + "---|" + ("---|" if with_goals else "")]
    rows += [f"| {i['id']} | {cell(i['kind'])} | {cell(i['text'])} | {i['grade']} |"
             + (f" {i['issue_link']} |" if with_issues else "") + f" {cell(i['turn'])} |"
             + (f" {i['goal']} |" if with_goals else "")
             for i in sort_items(items)]
    return "\n".join(rows)


def summary_table(items):
    """The one-off table for the session start: titles and meta only, no task text."""
    rows = ["| 번호 | 제목 | 구분 | 등급 | 차례 |", "|---|---|---|---|---|"]
    rows += [f"| {i['id']} | {cell(i['title'] or i['text'])} | {cell(i['kind'])} | {i['grade']} | {cell(i['turn'])} |"
             for i in sort_items(items)]
    return "\n".join(rows)


def active_table(items, *, with_issues=False):
    rows = ["| 번호 | 하는 일 | 멈춘 곳 | 다음 걸음 |" + (" 이슈 |" if with_issues else ""),
            "|---|---|---|---|" + ("---|" if with_issues else "")]
    rows += [f"| {i['id']} | {cell(i['title'])} | {cell(i['stopped'])} | {cell(i['next'])} |"
             + (f" {i['issue_link']} |" if with_issues else "")
             for i in sort_items(items) if i["active"]]
    return "\n".join(rows)


def utf16_width(text):
    return len(text.encode("utf-16-le")) // 2


def align_table(table):
    """Pad a table's cells like jk-wiki's fmt_tables.py (UTF-16 width, min 3), so its pre-commit check passes."""
    rows = [re.split(r"(?<!\\)\|", line.strip()[1:-1]) for line in table.split("\n")]
    rows = [[c.strip() for c in row] for row in rows]
    widths = [max([3] + [utf16_width(row[k]) for n, row in enumerate(rows) if n != 1]) for k in range(len(rows[0]))]
    rows[1] = ["-" * w for w in widths]
    return "\n".join("| " + " | ".join(c + " " * (widths[k] - utf16_width(c)) for k, c in enumerate(row)) + " |"
                     for row in rows)


def block_pattern(name):
    return re.compile(rf"(<!-- tasks\.py:{re.escape(name)} 시작[^>]*-->)(.*?)(<!-- tasks\.py:{re.escape(name)} 끝 -->)", re.S)


def has_block(text, name):
    return bool(block_pattern(name).search(text))


def replace_block(text, name, table):
    """Replace the table between the tasks.py markers named name."""
    if not has_block(text, name):
        raise ValueError(f"'{name}' 사본 표시를 찾지 못함")
    return block_pattern(name).sub(lambda m: f"{m.group(1)}\n\n{table}\n\n{m.group(3)}", text, count=1)


def id_pattern(ticker):
    return r"#\d+" if ticker is None else rf"{re.escape(ticker)}-\d+"


def landed_ids(text, ticker):
    return set(re.findall(rf"^\|\s*({id_pattern(ticker)})\s*\|", text, re.M))


PLACEHOLDER = re.compile(r"\(요약 없음, 이슈 #\d+\)")


def placeholder_ids(text, ticker):
    """Ids of LANDED rows written before the closing comment arrived."""
    return {m.group(1) for m in re.finditer(rf"^\|\s*({id_pattern(ticker)})\s*\|(.*)$", text, re.M)
            if PLACEHOLDER.search(m.group(2))}


def kst_day(stamp):
    if not stamp:
        return date.today().isoformat()
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(KST).date().isoformat()


def landed_entry(issue, ticker, offset):
    """Return (id, day, change, model, now, warning) for a closed issue."""
    item = item_of(issue, ticker, offset)
    change, model, now, warning = None, "-", "", ""
    for comment in sorted(issue.get("comments") or [], key=comment_key):
        keyword, value = head_of(comment)
        fields = fields_of(comment)
        if keyword == "끝":
            change, model, now = fields.get("바뀐 것") or item["title"], value or "-", fields.get("지금 반영", "")
        elif keyword == "취소":
            change, model, now = "취소: " + (fields.get("이유") or "이유 미기록"), "-", ""
        elif keyword == REOPENED:
            change, model, now = None, "-", ""
    if change is None:
        change = f"{item['title']} (요약 없음, 이슈 #{issue['number']})"
        warning = f"{item['id']}: 닫는 댓글(끝·취소)이 없어 제목으로 적었다"
    return item["id"], kst_day(issue.get("closedAt")), change, model, now, warning


def landed_header(lines):
    for index, line in enumerate(lines[:-1]):
        if re.match(r"^\|\s*번호\s*\|\s*날짜\s*\|", line) and set(lines[index + 1].replace("|", "").strip()) <= {"-", " "}:
            return index
    raise ValueError("LANDED 표를 찾지 못함")


def table_cells(line):
    return [part.strip() for part in re.split(r"(?<!\\)\|", line.strip()[1:-1])]


def landed_columns(text):
    lines = text.split("\n")
    return table_cells(lines[landed_header(lines)])


def has_goal_column(text):
    """True when a table in text already has the 목표 column."""
    return any("목표" in table_cells(line) for line in text.split("\n") if line.startswith("|"))


def add_landed_columns(text, names):
    """Append the missing columns to the LANDED table. Rows without a value for them get `-`."""
    lines = text.split("\n")
    start = landed_header(lines)
    columns = table_cells(lines[start])
    missing = [name for name in names if name not in columns]
    lines[start] = lines[start].rstrip() + "".join(f" {name} |" for name in missing)
    lines[start + 1] = lines[start + 1].rstrip() + "---|" * len(missing)
    for index in range(start + 2, len(lines)):
        if not lines[index].startswith("|"):
            break
        row = lines[index].rstrip()
        lines[index] = row + " - |" * (len(columns) + len(missing) - len(table_cells(row)))
    return "\n".join(lines)


def add_landed_issue_links(text, links, fit):
    """Write the 이슈 cell of every row in links, adding that column when the table has none, and align with fit."""
    lines = add_landed_columns(text, ["이슈"]).split("\n")
    start = landed_header(lines)
    column = table_cells(lines[start]).index("이슈")
    end = start + 2
    while lines[end:end + 1] and lines[end].startswith("|"):
        cells = re.split(r"(?<!\\)\|", lines[end].rstrip()[1:-1])
        link = links.get(cells[0].strip())
        if link and cells[column].strip() != link:
            cells[column] = f" {link} "
            lines[end] = "|" + "|".join(cells) + "|"
        end += 1
    return "\n".join(lines[:start] + fit("\n".join(lines[start:end])).split("\n") + lines[end:])


def landed_values(row):
    """Name the cells of (id, day, change, model[, goal])."""
    return dict(zip(("번호", "날짜", "바뀐 것", "모델", "목표"), [cell(value) for value in row]))


def insert_landed(text, rows):
    """Insert rows (id, day, change, model[, goal]) at the top of the LANDED table, keeping their order."""
    columns = landed_columns(text)
    lines = text.split("\n")
    index = landed_header(lines) + 2
    lines[index:index] = ["| " + " | ".join(landed_values(row).get(name, "-") for name in columns) + " |" for row in rows]
    return "\n".join(lines)


def update_landed(text, rows):
    """Rewrite the existing LANDED rows for these ids in place, leaving the columns that rows do not name."""
    wanted = {row[0]: landed_values(row) for row in rows}
    columns = landed_columns(text)
    lines = text.split("\n")
    for index, line in enumerate(lines):
        match = re.match(r"^\|\s*([^|\s]+)\s*\|", line)
        if match and match.group(1) in wanted:
            old = dict(zip(columns, table_cells(line)))
            new = {**old, **wanted.pop(match.group(1))}
            lines[index] = "| " + " | ".join(new.get(name, "-") for name in columns) + " |"
    return "\n".join(lines)


def drop_landed(text, ids):
    """Remove the LANDED rows of these ids (tasks that were reopened)."""
    return "\n".join(line for line in text.split("\n")
                     if not (re.match(r"^\|\s*([^|\s]+)\s*\|", line) and line.split("|")[1].strip() in ids))


# ---------- git·gh ----------

def git(*args, cwd=None):
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return done.stdout.strip() if done.returncode == 0 else None


def toplevel(cwd=None):
    return Path(git("rev-parse", "--show-toplevel", cwd=cwd) or (cwd or Path.cwd()))


def git_dir(cwd=None):
    found = git("rev-parse", "--path-format=absolute", "--git-dir", cwd=cwd)
    return Path(found) if found else Path(cwd or toplevel(cwd)) / ".git"


def session_path(cwd=None):
    """Per-worktree session state file under this worktree's own git dir."""
    return git_dir(cwd) / "tasks-session.json"


def load_session(cwd=None):
    try:
        data = json.loads(session_path(cwd).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_session(who, ref=None, cwd=None, issue_number=None):
    data = {"who": who}
    if ref:
        data["ref"] = ref
        if issue_number is not None:
            data["issue_number"] = issue_number
    try:
        path = session_path(cwd)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text(path, json.dumps(data, ensure_ascii=False) + "\n")
    except OSError:
        pass


def clear_session_ref(tid, cwd=None):
    session = load_session(cwd)
    if session.get("who") and session.get("ref") == tid:
        save_session(session["who"], ref=None, cwd=cwd)


def resolve_ref(args_ref, cwd=None):
    ref = args_ref or load_session(cwd).get("ref")
    if not ref:
        raise SystemExit("이 워크트리에서 잡은 일이 없다. 할 일 번호를 함께 준다")
    return ref


def session_issue(session, ref, ticker):
    tid, number = session.get("ref"), session.get("issue_number")
    if isinstance(tid, str) and type(number) is int and number > 0:
        if ticker is None:
            # 옛 방식일 때 저장한 `<티커>-n`은 이슈 번호와 다르므로 쓰지 않는다.
            return number if tid == f"#{number}" and ref.strip() in (tid, str(number)) else None
        if ref.strip() in (tid, tid.rsplit("-", 1)[-1], f"#{number}"):
            return number
    return None


def common_dir(cwd=None):
    found = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)
    return Path(found) if found else None


def main_folder(cwd=None):
    """The main worktree folder: the parent of the shared .git directory."""
    shared = common_dir(cwd)
    return shared.parent if shared else Path(cwd or toplevel())


def in_linked_worktree(cwd=None):
    own = git("rev-parse", "--path-format=absolute", "--git-dir", cwd=cwd)
    shared = common_dir(cwd)
    return bool(own and shared and Path(own).resolve() != shared.resolve())


def default_branch(cwd=None):
    """The default branch name from origin/HEAD, else origin/main or origin/master."""
    head = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=cwd)
    if head and "/" in head:
        return head.split("/", 1)[1]
    for name in ("main", "master"):
        if git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}", cwd=cwd):
            return name
    return None


def check_main(cwd=None, pull=False):
    """Stop unless the main folder is on the default branch and not behind origin. Returns a notice or ''."""
    if not git("remote", "get-url", "origin", cwd=cwd):
        return "origin 원격이 없어 기본 브랜치 확인을 건너뛰었다"
    fetched = git("fetch", "--quiet", "origin", cwd=cwd) is not None
    branch = default_branch(cwd)
    if not branch:
        return "origin의 기본 브랜치를 찾지 못해 확인을 건너뛰었다"
    current = git("branch", "--show-current", cwd=cwd)
    if current != branch:
        raise SystemExit(f"sync는 주 폴더의 기본 브랜치({branch})에서 한다. 지금: {current or 'detached HEAD'}. "
                         f"`git switch {branch}` 뒤 다시 sync한다")
    behind = int(git("rev-list", "--count", f"HEAD..origin/{branch}", cwd=cwd) or 0)
    if behind and not pull:
        raise SystemExit(f"주 폴더가 origin/{branch}보다 {behind}커밋 뒤처졌다. 뒤처진 채 사본을 쓰면 ship의 직접 푸시가 "
                         f"거절된다. `git pull --ff-only` 뒤 다시 sync하거나 `tasks.py sync --pull`을 쓴다")
    if behind:
        if git("pull", "--ff-only", "--quiet", "origin", branch, cwd=cwd) is None:
            raise SystemExit(f"`git pull --ff-only origin {branch}`가 실패했다. 주 폴더의 갈라짐이나 고친 파일을 먼저 정리한다")
        print(f"origin/{branch}의 {behind}커밋을 받았다")
    return "" if fetched else f"origin을 받지 못해 마지막으로 받은 origin/{branch}와 비교했다"


class GH:
    def __init__(self, cwd, timeout=30):
        self.cwd, self.timeout = str(cwd), timeout

    def run(self, *args, stdin=None):
        try:
            done = subprocess.run(["gh", *args], cwd=self.cwd, capture_output=True, text=True, encoding="utf-8",
                                  timeout=self.timeout, input=stdin)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise GhError(str(error)) from error
        if done.returncode != 0:
            raise GhError((done.stderr or done.stdout).strip(), done.stdout)
        if args[:2] == ("issue", "close") and "--comment" in args:
            return done.stdout + done.stderr
        return done.stdout

    def list(self, state, fields, *extra, limit=200):
        """List issues, raising the limit until the answer is shorter than it, so nothing is cut at a fixed cap."""
        while True:
            found = json.loads(self.run("issue", "list", "--state", state, "--limit", str(limit), "--json", fields, *extra) or "[]")
            if len(found) < limit:
                return found
            limit *= 4

    def issues(self, state):
        """Issues with bodies and comments. Use for open issues; closed ones go through brief() and issue()."""
        return self.list(state, FIELDS)

    def brief(self, state):
        """Issues without bodies and comments."""
        return self.list(state, BRIEF)

    def repository(self):
        """The name of the repository the issue commands write to."""
        return json.loads(self.run("repo", "view", "--json", "name"))["name"]

    def issue(self, number):
        return json.loads(self.run("issue", "view", str(number), "--json", FIELDS))

    def failed(self):
        """Open and closed issues that still carry the 막을 것 label."""
        return self.list("all", FIELDS, "--label", FAILED)

    def graph_repository(self, query):
        try:
            raw = self.run("api", "graphql", "-F", "owner={owner}", "-F", "name={repo}", "-f", "query=" + query)
        except GhError as error:
            try:
                return readable_part(error.stdout)["data"]["repository"]
            except (ValueError, KeyError, TypeError, IndexError):
                raise error from None
        return json.loads(raw)["data"]["repository"]

    def view(self, number):
        """One issue with its parents in a single call."""
        query = ("query($owner:String!, $name:String!) { repository(owner:$owner, name:$name) {\n"
                 f"i{number}:issue(number:{number}) {{ ...TaskIssue }}\n}} }}\nfragment TaskIssue on Issue {{{ISSUE_FIELDS}}}")
        try:
            return flatten_issue(self.graph_repository(query)[f"i{number}"])
        except (GhError, ValueError, KeyError, TypeError):
            issue = self.issue(number)
            self.attach_parents([issue])
            return issue

    def attach_parents(self, issues):
        """Read the parents of issues that came without them. They stay without `parent` when GitHub does not answer."""
        issues = [issue for issue in issues if "parent" not in issue]
        for start in range(0, len(issues), 50):
            batch = issues[start:start + 50]
            selections = "\n".join(f"i{i['number']}:issue(number:{i['number']}) {{ {PARENT_FIELDS} }}" for i in batch)
            try:
                data = self.graph_repository("query($owner:String!, $name:String!) { repository(owner:$owner, name:$name) {\n"
                                             + selections + "\n} }")
                for issue in batch:
                    issue["parent"] = data[f"i{issue['number']}"]["parent"]
            except (GhError, ValueError, KeyError, TypeError):
                continue

    def node(self, number, owner=None, name=None):
        """Return {id, url, parent} of an issue here, or in owner/name."""
        where = ("-f", f"owner={owner}", "-f", f"name={name}") if owner else ("-F", "owner={owner}", "-F", "name={repo}")
        raw = self.run("api", "graphql", *where, "-F", f"number={number}", "-f", "query=" + NODE)
        found = json.loads(raw)["data"]["repository"]["issue"]
        if not found:
            raise GhError(f"이슈 #{number}을 읽지 못함")
        return found

    def add_parent(self, parent_id, child_url):
        self.run("api", "graphql", "-f", f"parent={parent_id}", "-f", f"child={child_url}", "-f", "query=" + ADD_PARENT)

    def drop_parent(self, parent_id, child_id):
        self.run("api", "graphql", "-f", f"parent={parent_id}", "-f", f"child={child_id}", "-f", "query=" + DROP_PARENT)

    def open_and_failed(self):
        try:
            data = self.graph_repository(OPEN_AND_FAILED)
            return issue_connection(data["opened"]), issue_connection(data["failed"])
        except (GhError, ValueError, KeyError, TypeError) as error:
            # Larger repositories use the same paged listing as the individual commands.
            with ThreadPoolExecutor(max_workers=2) as workers:
                opened = workers.submit(self.issues, "open")
                failures = workers.submit(self.failed)
                found = opened.result(), failures.result()
            if not isinstance(error, GhError):  # gh가 실패했으면 훅 시간을 더 쓰지 않는다
                self.attach_parents(found[0])
            return found

    def issue_details(self, numbers):
        details, without_parents = {}, []
        for start in range(0, len(numbers), 50):
            batch = numbers[start:start + 50]
            if len(batch) == 1:
                details[batch[0]] = self.issue(batch[0])
                without_parents.append(details[batch[0]])
                continue
            selections = "\n".join(f"i{n}:issue(number:{n}) {{ ...TaskIssue }}" for n in batch)
            query = (
                "query($owner:String!, $name:String!) { repository(owner:$owner, name:$name) {\n"
                + selections + "\n} }\nfragment TaskIssue on Issue {" + ISSUE_FIELDS + "}"
            )
            try:
                data = self.graph_repository(query)
            except (GhError, ValueError, KeyError, TypeError):
                data = {}
            for number in batch:
                try:
                    details[number] = flatten_issue(data[f"i{number}"])
                except (ValueError, KeyError, TypeError):
                    details[number] = self.issue(number)
                    without_parents.append(details[number])
        self.attach_parents(without_parents)
        return details

    def comment(self, number, body):
        self.run("issue", "comment", str(number), "--body-file", "-", stdin=body)

    def edit(self, number, *args, stdin=None):
        self.run("issue", "edit", str(number), *args, stdin=stdin)

    def labels(self):
        return {label["name"] for label in json.loads(self.run("label", "list", "--limit", "500", "--json", "name") or "[]")}

    def ensure_labels(self, names):
        have = self.labels()
        for name in names:
            if name not in have:
                try:
                    self.run("label", "create", name, "--color", LABEL_COLORS.get(name.split(":", 1)[0], "ededed"))
                except GhError as error:
                    # 다른 세션이 같은 라벨을 먼저 만들었으면 그대로 쓴다.
                    if "already exists" not in str(error):
                        raise


def missing_label(error):
    # gh: "could not add label: 'x' not found"
    return "not found" in str(error).lower()


def with_labels(gh, labels, call):
    """Run call; only when GitHub says a label is missing, make the labels and run it again.

    Labels exist after the first use, so the common case asks GitHub nothing extra.
    """
    try:
        return call()
    except GhError as error:
        if not missing_label(error):
            raise
        gh.ensure_labels(labels)
        return call()


def cache_path(cwd=None):
    shared = common_dir(cwd)
    return (shared if shared else Path(cwd or toplevel()) / ".git") / "tasks-cache.json"


def issue_connection(connection):
    if any(connection["pageInfo"].values()):
        raise ValueError("이슈가 한 페이지보다 많음")
    return [flatten_issue(issue) for issue in connection["nodes"]]


def flatten_issue(issue):
    result = dict(issue)
    for field in ("labels", "comments"):
        connection = issue[field]
        if any(connection["pageInfo"].values()):
            raise ValueError(f"이슈 #{issue['number']}의 {field}가 한 페이지보다 많음")
        result[field] = connection["nodes"]
    return result


def read_cache(path):
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        age = datetime.now(KST) - datetime.fromisoformat(saved["at"])
        return saved["issues"], saved.get("failures", []), age.total_seconds()
    except (OSError, ValueError, TypeError, KeyError):
        return None


def write_cache(path, issues, failed):
    temporary = None
    try:
        saved = {"at": datetime.now(KST).isoformat(), "issues": issues, "failures": failed}
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(saved, handle, ensure_ascii=False)
        temporary.replace(path)
    except OSError:
        if temporary:
            temporary.unlink(missing_ok=True)


def fetch_open(gh, offline=False, cwd=None, prefer_cache=False, path=None):
    """Return (open issues or None, issues with unblocked failures, notice).

    Falls back to the last copy when GitHub is unreachable.
    """
    path = path or cache_path(cwd)
    if prefer_cache and not offline:
        cached = read_cache(path)
        if cached and 0 <= cached[2] < CACHE_TTL_SECONDS:
            return cached[0], cached[1], ""
    error = "오프라인으로 요청함"
    if not offline:
        try:
            issues, failed = gh.open_and_failed()
            write_cache(path, issues, failed)
            return issues, failed, ""
        except GhError as failure:
            error = str(failure).splitlines()[0] if str(failure) else "gh 실패"
    cached = read_cache(path)
    if cached is None:
        return None, [], f"이슈를 받지 못했고 저장한 사본도 없다 ({error})"
    issues, failed, age = cached
    return issues, failed, f"이슈를 받지 못해 {int(age // 60)}분 전 사본을 보인다 ({error})"


def print_failures(failed, ticker, offset):
    lines = failure_lines(failed, ticker, offset)
    if lines:
        print("\n막지 않은 실패 (같은 실패를 되풀이하지 않게 먼저 읽고, 막을 수 있으면 막는다):")
        print("\n".join(lines))


def print_stale_claims(items, now=None, hours=STALE_HOURS):
    lines = stale_claim_lines(items, now=now, hours=hours)
    if lines:
        print(f"\n오래된 선점 ({hours}시간 이상 갱신 없음):")
        print("\n".join(lines))


def print_unlinked(items):
    lines = [f"- {i['id']} {i['title']}" for i in sort_items(items) if i["unlinked"]]
    if lines:
        own = "이슈 번호" if lines[0].startswith("- #") else "티커-n"
        print(f"\n목표도 부모도 없는 열린 이슈 (`tasks.py edit <번호> --goal <G번호>`나 `--parent <{own}|이슈 URL>`로 잇는다):")
        print("\n".join(lines))


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def resolve(gh, ref, ticker, offset, read=None):
    """Return the issue for `n`, `#n` or `저장소#n`. read gets one issue (gh.issue).

    With a ticker: `<ticker>-n`, `n` (ticker number) or `#n` (issue number).
    """
    ref, read = ref.strip(), read or gh.issue
    if ticker is None:
        issue = read(number_here(ref, gh.repository))
        if is_pull(issue):  # gh issue view는 PR 번호에도 답한다
            raise SystemExit(f"#{issue['number']}은 이슈가 아니라 PR이라 아무것도 하지 않았다")
        return issue
    if ref.startswith("#"):
        return read(int(ref[1:]))
    number = id_number(ref) if "-" in ref else int(ref)
    want = f"{ticker}-{number}"
    guess = number - offset
    if guess > 0:
        try:
            issue = read(guess)
            if ticker_of(issue["title"], ticker)[0] == want:
                return issue
        except GhError:
            pass
    for issue in gh.brief("all"):
        if ticker_of(issue["title"], ticker)[0] == want:
            return read(issue["number"])
    raise SystemExit(f"{want} 이슈를 찾지 못함")


def load_overdue():
    spec = importlib.util.spec_from_file_location("overdue", SCRIPTS / "overdue.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------- 명령 ----------

def detail_lines(issue, ticker, offset, now=None):
    """Lines describing one issue: the full task text, turn, holder, note and unblocked failures."""
    item = item_of(issue, ticker, offset)
    number = "" if ticker is None else f"#{issue['number']}, "
    lines = [f"## {item['id']} ({number}{issue.get('state', '')}) {item['title']}", "", item["text"], "",
             f"- 구분: {item['kind']} · 등급: {item['grade']} · 차례: {item['turn']}",
             f"- 목표: {goal_path(issue, numbered=ticker is None)}",
             f"- 잡은 세션: {item['holder'] or '-'} · 멈춘 곳: {item['stopped']} · 다음 걸음: {item['next']}"]
    loc = [f"{k}: {item[f]}" for k, f in (("브랜치", "branch"), ("워크트리", "worktree"), ("시각", "claimed_at")) if item.get(f)]
    if loc:
        lines.append("- 선점 정보: " + " · ".join(loc))
    age = claim_age_hours(item, now=now)
    if age is not None and age >= STALE_HOURS:
        lines.append(f"- 오래된 선점: {int(age)}시간 전 — 멈춘 세션이면 `tasks.py release {typed(item['id'])} --force`로 놓는다")
    lines += [f"- 막지 않은 실패: {what} ({who})" for who, what in open_failures(issue.get("comments"))]
    return lines


def cmd_show(args, gh, ticker, offset, cwd=None):
    if args.ref:
        cached = read_cache(cache_path(cwd))
        if cached and (args.offline or 0 <= cached[2] < CACHE_TTL_SECONDS):
            ref = args.ref.strip()
            if ticker is None:
                saved = cached[0] + cached[1]
                number = number_here(ref, gh.repository if gh and not args.offline else
                                     lambda: next(map(repo_of, saved), ""))
                ref = f"#{number}"
            else:
                number = int(ref[1:] if ref.startswith("#") else ref.rsplit("-", 1)[-1])
            for issue in cached[0] + cached[1]:
                tid = item_of(issue, ticker, offset)["id"]
                if (ref.startswith("#") and issue["number"] == number) or (
                    not ref.startswith("#") and tid == f"{ticker}-{number}"
                ):
                    if args.offline:
                        print(f"> {int(cached[2] // 60)}분 전 사본을 보인다 (오프라인으로 요청함)\n")
                    elif gh is not None:
                        gh.attach_parents([issue])
                    print("\n".join(detail_lines(issue, ticker, offset)))
                    return
        if args.offline:
            raise SystemExit("저장한 사본에서 이슈를 찾지 못함")
        print("\n".join(detail_lines(resolve(gh, args.ref, ticker, offset, read=gh.view), ticker, offset)))
        return
    issues, failed, notice = fetch_open(gh, args.offline, cwd, prefer_cache=True)
    if issues is None:
        raise SystemExit(notice)
    items = [item_of(issue, ticker, offset) for issue in issues if is_task(issue, ticker)]
    if notice:
        print(f"> {notice}\n")
    print("## 일회성\n\n" + tasks_table(items) + "\n\n## 진행 중\n\n" + active_table(items))
    print_stale_claims(items)
    print_failures(failed, ticker, offset)


def cmd_hook(args, gh, ticker, offset, cwd=None):
    """Print what a session needs at start: a short table, what is held, failures and overdue items.

    The task text and the usage header of TASKS.md are left out; `show <번호>` prints one task in full.
    """
    path = cache_path(cwd)
    main = path.parent.parent
    text = (main / "TASKS.md").read_text(encoding="utf-8")
    issues, failed, notice = fetch_open(gh, args.offline, path=path)
    if notice:
        print(f"> {notice}\n")
    if issues is not None:
        items = [item_of(issue, ticker, offset) for issue in issues if is_task(issue, ticker)]
        table = summary_table(items)
        print(f"## 일회성 (열린 이슈 {len(items)}개, 위가 먼저)\n\n{table}")
    else:
        # 이슈도 저장한 사본도 없으면 파일의 사본 표를 그대로 보인다.
        items = []
        found = block_pattern("일회성").search(text)
        table = found.group(2).strip() if found else ""
        print("## 일회성 (TASKS.md 사본)\n\n" + (table or "(사본 표 없음)"))
    print("\n할 일 전체와 끝 조건: `tasks.py show <번호>`. 명령은 TASKS.md '일회성' 머리말.")
    print("\n## 진행 중 (이슈)\n\n" + active_table(items))
    print_stale_claims(items)
    print_unlinked(items)
    if Path(cwd or toplevel()).resolve() != main.resolve():
        print(f"\n> 이 폴더는 worktree다. TASKS.md·STATE.md·LANDED.md를 고치지 않는다. 주 폴더: {main}")
    print_failures(failed, ticker, offset)
    overdue = load_overdue()
    due = overdue.due_items(text, date.today())
    waits = overdue.passed_waits("## 일회성\n\n" + table, datetime.now())
    if due:
        print("\n밀린 주기적 항목:")
        for task, reason in due:
            print(f"- {task} ({reason})")
    if waits:
        print("\n날짜가 지난 대기 항목:")
        for number, turn in waits:
            print(f"- {number} ({turn})")


def task_copy_warning(root):
    scripts = root / "scripts"
    if not (scripts / "tasks.json").is_file():
        return ""
    try:
        source = (scripts / "tasks.py").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    marker = re.search(r"^TASKS_SCRIPT_VERSION\s*=\s*([0-9]+)\s*(?:#.*)?$", source, re.MULTILINE)
    version = int(marker[1]) if marker else 0
    if version < TASKS_SCRIPT_VERSION:
        return "저장소의 scripts/tasks.py 사본이 jk-template 공통본보다 오래됐다. 주 폴더에서 install_tasks.py --upgrade로 갱신한다."
    return ""


def goals_arg(args):
    """The --goal value as a list, or None when it was not given."""
    goals = getattr(args, "goal", None)
    return parse_goals(goals) if isinstance(goals, str) else goals


def parent_node(gh, ref, ticker, offset):
    """Return the GitHub node of a task number in this repository or of an issue URL in any repository."""
    url = PARENT_URL.fullmatch(ref)
    if url:
        return gh.node(int(url.group(3)), url.group(1), url.group(2))
    if ticker is not None and ref.rsplit("-", 1)[0] != ticker:
        raise SystemExit(f"{ref}은 이 저장소({ticker})의 할 일이 아니다. 다른 저장소의 부모는 이슈 URL로 준다")
    return gh.node(resolve(gh, ref, ticker, offset)["number"])


def cmd_add(args, gh, ticker, offset):
    if args.turn == "대기" and not args.wait:
        raise SystemExit("차례가 대기면 --wait에 조건을 적는다")
    if args.id and ticker is None:
        raise SystemExit("이 저장소의 번호는 이슈 번호라 --id를 쓰지 않는다")
    ref = getattr(args, "parent", None)
    parent = parent_node(gh, ref, ticker, offset) if ref else None
    order = args.order
    if order is None:
        # 순서만 보면 되므로 본문만 받는다(댓글·라벨은 받지 않는다).
        orders = [parse_body(i.get("body"))[1].get("순서", "") for i in gh.list("open", "number,body")]
        order = max([int(o) for o in orders if o.isdigit()] or [0]) + 10
    labels = [f"구분:{args.kind}", f"등급:{args.grade}", f"차례:{args.turn}"]
    labels += goal_labels(goals_arg(args) or [])
    body = make_body(args.text, {"순서": order, "대기": args.wait})
    title = f"{args.id} {args.title}" if args.id else args.title
    url = with_labels(gh, labels, lambda: gh.run("issue", "create", "--title", title, "--body-file", "-",
                                                 "--label", ",".join(labels), stdin=body)).strip()
    number = int(url.rstrip("/").rsplit("/", 1)[1])
    tid = args.id or task_id({"number": number}, ticker, offset)
    if not args.id and ticker is not None:
        gh.edit(number, "--title", f"{tid} {args.title}")
    print(f"{tid} {url}" if ticker is None else f"{tid} (#{number}) {url}")
    if parent:
        try:
            gh.add_parent(parent["id"], url)
        except GhError as error:
            raise SystemExit(f"{tid} 이슈는 만들었지만 부모를 걸지 못했다({error}). "
                             f"다시 만들지 말고 `tasks.py edit {typed(tid)} --parent {typed(ref)}`로 건다")


def cmd_edit(args, gh, ticker, offset):
    issue = resolve(gh, args.ref, ticker, offset)
    tid = item_of(issue, ticker, offset)["id"]
    named = ticker_of(issue.get("title"), ticker)[0]
    flags, add, drop, body = [], [], [], None
    ref, no_parent, goals = getattr(args, "parent", None), getattr(args, "no_parent", False), goals_arg(args)
    if args.title:
        flags += ["--title", f"{named} {args.title}" if named else args.title]
    if args.text is not None or args.order is not None:
        text, meta = parse_body(issue.get("body"))
        if args.text is not None:
            text = args.text
        if args.order is not None:
            meta["순서"] = args.order
        body = make_body(text, meta)
        flags += ["--body-file", "-"]
    for prefix, new in (("구분", [f"구분:{args.kind}"] if args.kind else None),
                        ("목표", goal_labels(goals) if goals is not None else None)):
        if new is not None:
            add += new
            drop += [n for n in label_names(issue) if n.startswith(prefix + ":") and n not in new]
    flags += (["--add-label", ",".join(add)] if add else []) + (["--remove-label", ",".join(drop)] if drop else [])
    if not flags and not ref and not no_parent and goals is None:
        raise SystemExit("바꿀 것이 없다: --title, --text, --kind, --order, --goal, --parent, --no-parent 중 하나 이상을 준다")
    # 부모를 읽지 못하면 아무것도 고치지 않고 멈춘다.
    parent = parent_node(gh, ref, ticker, offset) if ref else None
    child = gh.node(issue["number"]) if ref or no_parent else None
    if parent and parent["id"] == child["id"]:
        raise SystemExit(f"{tid}을 자기 부모로 걸 수 없다")
    if flags:
        with_labels(gh, add, lambda: gh.edit(issue["number"], *flags, stdin=body))
    old = (child.get("parent") or {}).get("id") if child else None
    if parent and parent["id"] != old:
        gh.add_parent(parent["id"], child["url"])
    if no_parent:
        if old:
            gh.drop_parent(old, child["id"])
        else:
            print(f"{tid}에 뗄 부모가 없다")
    print(f"{tid}을 고쳤다")


def cmd_claim(args, gh, ticker, offset, cwd=None):
    issue = resolve(gh, args.ref, ticker, offset)
    tid = item_of(issue, ticker, offset)["id"]
    if issue["state"] != "OPEN":
        raise SystemExit(f"{tid}은 닫혀 있다")
    session = load_session(cwd)
    root = toplevel(cwd)
    # 저장된 이름은 저장된 ref가 이번에 잡는 할 일과 같을 때만 쓴다. release·close 뒤에 남은 이름을 다른 일에 쓰지 않는다.
    saved = session.get("who") if session.get("ref") == tid else None
    who = args.who or saved or f"{root.name}-{secrets.token_hex(2)}"
    info = claim_info(issue["comments"])
    holder = info["holder"]
    if holder == who:
        save_session(who, ref=tid, cwd=cwd, issue_number=issue["number"])
        print(f"{tid}은 이미 {who}가 잡고 있다")
        return
    if holder:
        extra = f" (브랜치: {info['branch']})" if info["branch"] else ""
        age = claim_age_hours(info)
        hint = (f". {int(age)}시간 전 선점이라 멈춘 세션이면 `tasks.py release {typed(tid)} --force` 뒤 다시 잡는다"
                if age is not None and age >= STALE_HOURS else "")
        raise SystemExit(f"{tid}은 {holder}{extra}가 잡고 있어 하지 않는다{hint}")
    started = time.monotonic()
    with_labels(gh, [ACTIVE], lambda: gh.edit(issue["number"], "--add-label", ACTIVE))
    branch = git("branch", "--show-current", cwd=cwd) or "detached HEAD"
    at = datetime.now(KST).isoformat(timespec="seconds")
    gh.comment(issue["number"], f"잡음: {who}\n브랜치: {branch}\n워크트리: {root}\n시각: {at}")
    save_session(who, ref=tid, cwd=cwd, issue_number=issue["number"])
    time.sleep(max(0, args.settle - (time.monotonic() - started)))
    holder, _ = claim_state(gh.issue(issue["number"])["comments"])
    if holder != who:
        save_session(session.get("who") or who, ref=session.get("ref"), cwd=cwd,
                     issue_number=session.get("issue_number"))
        raise SystemExit(f"{holder}가 먼저 잡았다. {tid}은 하지 않는다")
    print(f"{tid}을 잡았다. 이름: {who}" if ticker is None else f"{tid} (#{issue['number']})을 잡았다. 이름: {who}")


def cmd_note(args, gh, ticker, offset, cwd=None):
    ref = resolve_ref(args.ref, cwd=cwd)
    session = load_session(cwd)
    number = session_issue(session, ref, ticker)
    tid = session.get("ref")
    who = args.who or session.get("who")
    if number is None or not who:
        issue = resolve(gh, ref, ticker, offset)
        number = issue["number"]
        tid = item_of(issue, ticker, offset)["id"]
        holder, _ = claim_state(issue["comments"])
        who = who or holder or "-"
    gh.comment(number, f"메모: {who}\n멈춘 곳: {args.stopped}\n다음 걸음: {args.next}")
    print(f"{tid}에 메모를 남겼다")


def cmd_turn(args, gh, ticker, offset):
    issue = resolve(gh, args.ref, ticker, offset)
    turn, wait = args.turn, None
    if turn.startswith("대기"):
        turn, wait = "대기", turn.split(":", 1)[1].strip() if ":" in turn else ""
        if not wait:
            raise SystemExit('대기는 "대기: 조건"으로 준다')
    if turn not in TURNS:
        raise SystemExit(f"차례는 {', '.join(TURNS)} 중 하나")
    names = label_names(issue)
    add = [f"차례:{turn}"] + ([f"등급:{args.grade}"] if args.grade else [])
    drop = [n for n in names if (n.startswith("차례:") or (args.grade and n.startswith("등급:"))) and n not in add]
    labels = ["--add-label", ",".join(add)] + (["--remove-label", ",".join(drop)] if drop else [])
    text, meta = parse_body(issue.get("body"))
    meta["대기"] = wait
    # 본문이 `-`로 시작하거나 길어도 깨지지 않게 인자가 아닌 stdin으로 넘긴다.
    with_labels(gh, add, lambda: gh.edit(issue["number"], *labels, "--body-file", "-", stdin=make_body(text, meta)))
    print(f"{item_of(issue, ticker, offset)['id']} 차례: {args.turn}")


def cmd_release(args, gh, ticker, offset, cwd=None):
    ref = resolve_ref(args.ref, cwd=cwd)
    issue = resolve(gh, ref, ticker, offset)
    tid = item_of(issue, ticker, offset)["id"]
    holder, _ = claim_state(issue["comments"])
    who = args.who or load_session(cwd).get("who")
    if holder and who != holder and not args.force:
        raise SystemExit(f"{holder}가 잡은 일이다. 놓으려면 --who {holder} 또는 --force")
    gh.comment(issue["number"], f"놓음: {who or holder or '-'}")
    if ACTIVE in label_names(issue):
        gh.edit(issue["number"], "--remove-label", ACTIVE)
    clear_session_ref(tid, cwd=cwd)
    print(f"{tid}을 놓았다")


def finish(gh, issue, body, reason):
    gh.comment(issue["number"], body)
    if ACTIVE in label_names(issue):
        gh.edit(issue["number"], "--remove-label", ACTIVE)
    if issue["state"] == "OPEN":
        gh.run("issue", "close", str(issue["number"]), "--reason", reason)


def effect_arg(args):
    return " ".join((getattr(args, "effect", None) or "").split())


def require_effect(issue, tid, effect):
    goals = needs_effect(issue)
    if goals and not effect:
        raise SystemExit(f"{tid}은 목표 {'·'.join(goals)} 라벨이 있어 전후 없이 닫지 않는다. `--effect \"<전 → 후>\"`를 주거나, "
                         f"전후를 적을 수 없으면 `tasks.py edit {typed(tid)} --goal G0`으로 바꾼 뒤 닫는다")


def close_command(args, gh, ticker, offset, cwd=None):
    """close from the command line: the claimed-issue shortcut of cmd_close does not read labels, so read them here."""
    number = session_issue(load_session(cwd), args.ref, ticker)
    if number is not None and not effect_arg(args):
        issue = gh.issue(number)
        require_effect(issue, item_of(issue, ticker, offset)["id"], "")
    cmd_close(args, gh, ticker, offset, cwd=cwd)


def cmd_close(args, gh, ticker, offset, cwd=None):
    effect = effect_arg(args)
    session = load_session(cwd)
    number = session_issue(session, args.ref, ticker)
    if number is None:
        issue = resolve(gh, args.ref, ticker, offset)
        number = issue["number"]
        tid = item_of(issue, ticker, offset)["id"]
        require_effect(issue, tid, effect)
        closed = issue["state"] != "OPEN"
        active = ACTIVE in label_names(issue)
    else:
        tid = session["ref"]
        closed, active = False, True
    body = f"끝: {args.model}\n바뀐 것: {' '.join(args.summary.split())}"
    if effect:
        body += f"\n전후: {effect}"
    if args.now:
        body += f"\n지금 반영: {' '.join(args.now.split())}"
    if not closed:
        output = gh.run("issue", "close", str(number), "--reason", "completed", "--comment", body)
        # gh does not post the comment if it finds the issue already closed.
        closed = any(line.rstrip().endswith(" is already closed") for line in output.splitlines())
    if closed:
        gh.comment(number, body)
    if active:
        try:
            gh.edit(number, "--remove-label", ACTIVE)
        except GhError as error:
            if not missing_label(error):
                raise
    clear_session_ref(tid, cwd=cwd)
    already = " (이미 닫힌 이슈라 댓글만 남겼다)" if closed else ""
    print(f"{tid}을 끝냈다{already}. LANDED.md는 주 폴더의 sync가 채운다")


def cmd_cancel(args, gh, ticker, offset, cwd=None):
    issue = resolve(gh, args.ref, ticker, offset)
    tid = item_of(issue, ticker, offset)["id"]
    finish(gh, issue, f"취소: {args.who or '-'}\n이유: {' '.join(args.reason.split())}", "not planned")
    clear_session_ref(tid, cwd=cwd)
    print(f"{tid}을 취소했다. LANDED.md는 주 폴더의 sync가 채운다")


def cmd_reopen(args, gh, ticker, offset):
    issue = resolve(gh, args.ref, ticker, offset)
    tid = item_of(issue, ticker, offset)["id"]
    if issue["state"] == "OPEN":
        raise SystemExit(f"{tid}은 이미 열려 있다")
    gh.run("issue", "reopen", str(issue["number"]))
    gh.comment(issue["number"], f"{REOPENED}: {args.who or '-'}\n이유: {' '.join(args.reason.split())}")
    print(f"{tid}을 다시 열었다. 주 폴더의 sync가 LANDED.md에서 그 행을 빼고 표에 되돌린다")


def cmd_fail(args, gh, ticker, offset):
    issue = resolve(gh, args.ref, ticker, offset)
    holder, _ = claim_state(issue["comments"])
    gh.comment(issue["number"], f"실패: {args.who or holder or '-'}\n무엇: {' '.join(args.what.split())}")
    if FAILED not in label_names(issue):
        with_labels(gh, [FAILED], lambda: gh.edit(issue["number"], "--add-label", FAILED))
    print(f"{item_of(issue, ticker, offset)['id']}에 실패를 남겼다. 막으면 tasks.py fixed로 지운다")


def cmd_fixed(args, gh, ticker, offset):
    issue = resolve(gh, args.ref, ticker, offset)
    if not open_failures(issue["comments"]):
        raise SystemExit(f"{item_of(issue, ticker, offset)['id']}에 막지 않은 실패가 없다")
    gh.comment(issue["number"], f"막음: {args.who or '-'}\n어떻게: {' '.join(args.how.split())}")
    if FAILED in label_names(issue):
        gh.edit(issue["number"], "--remove-label", FAILED)
    print(f"{item_of(issue, ticker, offset)['id']}의 실패를 막음으로 적었다")


def cmd_sync(args, gh, ticker, offset, cwd=None):
    if in_linked_worktree(cwd):
        raise SystemExit(f"sync는 주 폴더에서만 한다: {main_folder(cwd)}")
    root = main_folder(cwd)
    notice = check_main(root, pull=getattr(args, "pull", False))
    if notice:
        print(f"> {notice}")
    paths = {name: root / name for name in ("TASKS.md", "STATE.md", "LANDED.md")}
    texts = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}
    have, waiting = landed_ids(texts["LANDED.md"], ticker), placeholder_ids(texts["LANDED.md"], ticker)
    since = load_since(root / "scripts" / "tasks.json") if ticker is None else None

    def to_land(issue):
        """True for a closed task whose LANDED row is missing or still waits for its closing comment."""
        tid = task_id(issue, ticker, offset)
        return tid in waiting or (tid not in have and (since is None or kst_day(issue.get("closedAt")) >= since))

    every = gh.brief("all")
    numbers = []
    for issue in every:
        number = issue["number"]
        if FAILED in label_names(issue) or (is_task(issue, ticker) and (issue["state"] == "OPEN" or to_land(issue))):
            numbers.append(number)
    details = gh.issue_details(numbers)
    every = [details.get(issue["number"], issue) for issue in every]
    with_goals = all(goal_known(issue) for issue in details.values() if is_task(issue, ticker))
    if not with_goals:
        # 목표를 모르는 채 쓴 `-`는 미정으로 남으므로, 열이 이미 있으면 쓰지 않고 멈춘다.
        block = block_pattern("일회성").search(texts["TASKS.md"])
        if has_goal_column(texts["LANDED.md"]) or (block and has_goal_column(block.group(2))):
            raise SystemExit("부모 이슈를 읽지 못해 목표를 계산할 수 없다. 사본을 고치지 않았다. 잠시 뒤 다시 sync한다")
        print("> 부모 이슈를 읽지 못해 '목표' 열을 쓰지 않았다")
    failed = [issue for issue in every if FAILED in label_names(issue)]
    open_issues = [issue for issue in every if issue["state"] == "OPEN" and is_task(issue, ticker)]
    closed = [issue for issue in every if issue["state"] == "CLOSED" and is_task(issue, ticker)]
    skipped = len(every) - len(open_issues) - len(closed)
    for issue in open_issues + closed:
        tid, title = ticker_of(issue["title"], ticker)
        if ticker is not None and not tid:
            tid = f"{ticker}-{issue['number'] + offset}"
            gh.edit(issue["number"], "--title", f"{tid} {title}")
            issue["title"] = f"{tid} {title}"
            print(f"번호 붙임: #{issue['number']} → {tid}")
    for issue in open_issues:
        fixed = form_fix(issue)
        if not fixed:
            continue
        body, add, drop = fixed
        try:
            parse_goals(parse_form(issue["body"]).get("목표", UNDECIDED))
        except ValueError as error:
            print(f"확인: {item_of(issue, ticker, offset)['id']} 양식의 목표를 라벨로 바꾸지 않았다. {error}")
        flags = ["--body-file", "-"] + (["--add-label", ",".join(add)] if add else []) \
            + (["--remove-label", ",".join(drop)] if drop else [])
        with_labels(gh, add, lambda: gh.edit(issue["number"], *flags, stdin=body))
        issue["body"] = body
        kept = [n for n in label_names(issue) if n not in drop and n not in add]
        issue["labels"] = [{"name": n} for n in kept + add]
        print(f"양식 이슈 정리: {item_of(issue, ticker, offset)['id']} (본문·라벨)")
    for issue in closed:
        # `Closes #n`이 닫고 close가 아직 오지 않았거나 잊힌 이슈의 라벨
        if ACTIVE in label_names(issue):
            gh.edit(issue["number"], "--remove-label", ACTIVE)
            print(f"진행중 라벨 지움: {item_of(issue, ticker, offset)['id']} (닫힌 이슈)")
    items = [item_of(issue, ticker, offset) for issue in open_issues]
    new = dict(texts)
    fit = align_table if (root / ".wiki" / "config.json").is_file() else str
    new["TASKS.md"] = replace_block(texts["TASKS.md"], "일회성", fit(tasks_table(items, with_issues=True, with_goals=with_goals)))
    new["STATE.md"] = replace_block(texts["STATE.md"], "진행 중", fit(active_table(items, with_issues=True)))
    reopened = {i["id"] for i, issue in ((item_of(o, ticker, offset), o) for o in open_issues)
                if i["id"] in have and any(head_of(c)[0] == REOPENED for c in issue.get("comments") or [])}
    if reopened:
        new["LANDED.md"] = drop_landed(new["LANDED.md"], reopened)
        have -= reopened
    full = [issue for issue in closed if to_land(issue)]
    entries = [landed_entry(issue, ticker, offset) for issue in sorted(full, key=lambda i: i.get("closedAt") or "", reverse=True)]
    fresh = [e for e in entries if e[0] not in have]
    healed = [e for e in entries if e[0] in waiting and not e[5]]
    new["LANDED.md"] = add_landed_columns(new["LANDED.md"], ["이슈"] + (["목표"] if with_goals else []))
    goals = {item_of(issue, ticker, offset)["id"]: goal_cell(issue) for issue in full}
    if healed:
        new["LANDED.md"] = update_landed(new["LANDED.md"], [(*e[:4], goals[e[0]]) for e in healed])
    if fresh:
        new["LANDED.md"] = insert_landed(new["LANDED.md"], [(*e[:4], goals[e[0]]) for e in fresh])
    links = {task_id(issue, ticker, offset): issue_link(issue) for issue in closed if issue.get("url")}
    new["LANDED.md"] = add_landed_issue_links(new["LANDED.md"], links, fit)
    changed = [name for name in paths if new[name] != texts[name]]
    for name in changed:
        write_text(paths[name], new[name])
    print("바뀐 사본: " + (", ".join(changed) if changed else "없음"))
    for tid in sorted(reopened, key=id_number):
        print(f"LANDED에서 뺌: {tid} (다시 열림)")
    if skipped:
        titled = "" if ticker is None else "번호 제목도 "
        print(f"할 일이 아닌 이슈 {skipped}개는 건너뛰었다({titled}구분·등급·차례 라벨{'도' if titled else '이'} 없음). "
              f"할 일로 삼으려면 `tasks.py turn {'이슈번호' if ticker is None else '#이슈번호'} AI`")
    for tid, _, _, _, now, _ in fresh + healed:
        if tid in waiting:
            print(f"요약 채움: {tid} (닫는 댓글이 뒤에 왔다)")
        if now:
            print(f"STATE '지금'에 반영할 것 ({tid}): {now}")
    for tid, *_ in [e for e in entries if e[5] and (e[0] not in have or e[0] in waiting)]:
        print(f"확인: {tid}은 닫는 댓글(끝·취소)이 없어 LANDED에 제목으로 적었다. "
              f"`tasks.py close {typed(tid)} --model ... --summary ...`(또는 cancel)로 남기면 다음 sync가 그 행을 고친다")
    print_stale_claims(items)
    print_unlinked(items)
    print_failures(failed, ticker, offset)


def goal_option(text):
    try:
        return parse_goals(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error))


def parent_option(text):
    # 옛 방식의 저장소에서 쓸 수 없는 번호는 parent_node가 거른다.
    if not re.fullmatch(r"[A-Z]+-[1-9]\d*", text) and not REF.fullmatch(text) and not PARENT_URL.fullmatch(text):
        raise argparse.ArgumentTypeError(f"부모는 이슈 번호(옛 방식은 <티커>-n)나 https://github.com/<소유자>/<저장소>/issues/<n>으로 준다: {text}")
    return text


class TasksParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        found = super().parse_args(args, namespace)
        if getattr(found, "command", "") == "add" and found.parent is None and found.goal is None:
            self.error("add에는 --parent나 --goal이 필요하다. 판단이 서지 않으면 --goal 미정")
        return found


def parser():
    top = TasksParser(description=__doc__.split("\n")[0])
    sub = top.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show", help="이슈의 할 일과 진행 중을 표로 보인다. 번호를 주면 그 일 하나를 자세히 보인다")
    show.add_argument("ref", nargs="?", help='173, "#173" 또는 "저장소#173" (옛 방식: <티커>-n, n 또는 "#이슈번호")')
    show.add_argument("--offline", action="store_true")
    hook = sub.add_parser("hook", help="세션 시작 출력")
    hook.add_argument("--offline", action="store_true")
    hook.add_argument("--check-copy", action="store_true", help="플러그인 훅에 오래된 스크립트 사본 경고만 보낸다")
    add = sub.add_parser("add", help="할 일을 이슈로 만든다")
    add.add_argument("text", help="무엇이 되면 끝인지까지 적은 할 일")
    add.add_argument("--title", required=True)
    add.add_argument("--kind", required=True, help="구분 (예: 경계, 순서)")
    add.add_argument("--grade", required=True, choices=GRADES)
    add.add_argument("--turn", default="AI", choices=TURNS)
    add.add_argument("--wait", help="차례가 대기일 때의 조건")
    add.add_argument("--order", type=int, help="작을수록 먼저. 없으면 맨 뒤")
    add.add_argument("--id", help="옛 방식에서 옮겨 오는 항목의 기존 번호 (예: RAE-66)")
    add.add_argument("--parent", type=parent_option, help="부모 할 일: 이슈 번호(옛 방식은 <티커>-n), 다른 저장소는 이슈 URL. 목표를 물려받는다")
    add.add_argument("--goal", type=goal_option, help="G0–G8(G2–G8은 쉼표로 여럿)이나 미정. --parent와 함께 주면 하위의 덮어쓰기")
    edit = sub.add_parser("edit", help="제목·할 일·구분·순서·목표·부모를 고친다")
    edit.add_argument("ref")
    edit.add_argument("--title", help="번호를 뺀 새 제목")
    edit.add_argument("--text", help="무엇이 되면 끝인지까지 적은 새 할 일")
    edit.add_argument("--kind", help="새 구분")
    edit.add_argument("--order", type=int, help="새 순서. 작을수록 먼저")
    edit.add_argument("--goal", type=goal_option, help="새 목표. 미정이면 목표 라벨을 뗀다")
    family = edit.add_mutually_exclusive_group()
    family.add_argument("--parent", type=parent_option, help="새 부모: 이슈 번호(옛 방식은 <티커>-n), 다른 저장소는 이슈 URL")
    family.add_argument("--no-parent", action="store_true", help="부모를 뗀다")
    claim = sub.add_parser("claim", help="일을 잡는다. 먼저 잡은 세션이 한다")
    claim.add_argument("ref")
    claim.add_argument("--who")
    claim.add_argument("--settle", type=float, default=2.0, help="다른 세션의 잡음 댓글을 기다리는 초")
    note = sub.add_parser("note", help="멈춘 곳과 다음 걸음을 남긴다")
    note.add_argument("ref", nargs="?", help="생략하면 이 워크트리에서 잡은 일")
    note.add_argument("--stopped", required=True)
    note.add_argument("--next", required=True)
    note.add_argument("--who")
    turn = sub.add_parser("turn", help='차례를 바꾼다: AI, 사용자, "대기: 조건"')
    turn.add_argument("ref")
    turn.add_argument("turn")
    turn.add_argument("--grade", choices=GRADES)
    release = sub.add_parser("release", help="잡은 일을 놓는다")
    release.add_argument("ref", nargs="?", help="생략하면 이 워크트리에서 잡은 일")
    release.add_argument("--who")
    release.add_argument("--force", action="store_true")
    close = sub.add_parser("close", help="끝낸다")
    close.add_argument("ref")
    close.add_argument("--model", required=True)
    close.add_argument("--summary", required=True, help="LANDED '바뀐 것'에 들어갈 한 문장")
    close.add_argument("--now", help="STATE '지금'에 반영할 것")
    close.add_argument("--effect", metavar='"전 → 후"', help="일의 전후 한 줄. 자기 라벨이 G1–G8이면 꼭 준다")
    cancel = sub.add_parser("cancel", help="취소한다")
    cancel.add_argument("ref")
    cancel.add_argument("--reason", required=True)
    cancel.add_argument("--who")
    reopen = sub.add_parser("reopen", help="잘못 닫은 일을 다시 연다. sync가 LANDED에서 그 행을 뺀다")
    reopen.add_argument("ref")
    reopen.add_argument("--reason", required=True)
    reopen.add_argument("--who")
    fail = sub.add_parser("fail", help="실패를 남긴다. 막을 때까지 훅·show·sync가 보인다")
    fail.add_argument("ref")
    fail.add_argument("--what", required=True, help="무엇이 왜 실패했나 한 문장")
    fail.add_argument("--who")
    fixed = sub.add_parser("fixed", help="이슈의 실패를 모두 막았다고 적는다")
    fixed.add_argument("ref")
    fixed.add_argument("--how", required=True, help="막은 방법: 테스트 이름·검사·함정 줄·커밋")
    fixed.add_argument("--who")
    sync = sub.add_parser("sync", help="주 폴더의 TASKS·STATE·LANDED 사본을 이슈에 맞춘다")
    sync.add_argument("--pull", action="store_true", help="주 폴더가 origin보다 뒤처졌으면 git pull --ff-only로 받고 쓴다")
    return top


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    root = toplevel()
    if args.command == "hook" and args.check_copy:
        warning = task_copy_warning(root)
        if warning:
            print(json.dumps({"systemMessage": warning, "hookSpecificOutput": {
                "hookEventName": "SessionStart", "additionalContext": warning,
            }}, ensure_ascii=False))
        return
    ticker, offset = load_config(root / "scripts" / "tasks.json")
    gh = GH(root, timeout=8 if args.command == "hook" else 30)
    commands = {"show": cmd_show, "hook": cmd_hook, "add": cmd_add, "edit": cmd_edit, "claim": cmd_claim, "note": cmd_note,
                "turn": cmd_turn, "release": cmd_release, "close": close_command, "cancel": cmd_cancel, "reopen": cmd_reopen,
                "fail": cmd_fail, "fixed": cmd_fixed, "sync": cmd_sync}
    try:
        if args.command in ("hook", "show"):
            commands[args.command](args, gh, ticker, offset, cwd=root)
        else:
            commands[args.command](args, gh, ticker, offset)
    except GhError as error:
        raise SystemExit(f"gh 실패: {error}")
    finally:
        if args.command not in ("hook", "show"):
            try:
                cache_path(root).unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    main()
