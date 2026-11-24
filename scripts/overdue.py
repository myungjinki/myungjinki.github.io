"""Print TASKS.md items that need attention today.

- Periodic items that are due today or overdue.
- One-off items whose `대기:` turn names a date (and optional time) that has passed.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
import re
import sys

PERIODS = {"매일": 1, "매주": 7, "매월": 31, "매년": 365}
WAIT_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}))?")
DEFERRED = re.compile(r"다음 주기부터 \((\d{4}-\d{2}-\d{2})\)")


def next_due(last, period):
    """Return the next calendar boundary, or retain an existing interval."""
    if period == "연초":
        return date(last.year + 1, 1, 1)
    if period in ("분기초", "월초"):
        month = ((last.month - 1) // 3 + 1) * 3 + 1 if period == "분기초" else last.month + 1
        return date(last.year + (month > 12), (month - 1) % 12 + 1, 1)
    if period == "매주 월요일":
        return last + timedelta(days=7 - last.weekday())
    days = PERIODS.get(period)
    return last + timedelta(days=days) if days else None


def cells_of(line):
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def table_rows(section):
    """Yield the cells of each data row in a Markdown table section."""
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = cells_of(line)
        if cells[0] in ("할 일", "번호", "") or set(cells[0]) <= {"-"}:
            continue
        yield cells


def section_of(text, title):
    """Return the text under `## title` up to the next `## ` heading."""
    if f"## {title}" not in text:
        return ""
    return text.split(f"## {title}", 1)[1].split("\n## ", 1)[0]


def due_items(text, today):
    """Return (task, reason) pairs from the 주기적 table of a TASKS.md text."""
    items = []
    for cells in table_rows(section_of(text, "주기적")):
        if len(cells) != 3:
            continue
        task, period, last = cells
        if last == "아직 안 함":
            items.append((task, "아직 안 함"))
            continue
        deferred = DEFERRED.fullmatch(last)
        if deferred:
            last = deferred.group(1)
        match = re.fullmatch(r"\d{4}-\d{2}-\d{2}", last)
        due = next_due(date.fromisoformat(last), period) if match else None
        if due and due <= today:
            label = f"{last}에 다음 주기로 미룸" if deferred else f"마지막 {last}"
            items.append((task, f"{label}, {period}"))
    return items


def passed_waits(text, now):
    """Return (number, turn) pairs for 일회성 rows whose `대기:` date has passed."""
    items = []
    section = section_of(text, "일회성")
    # 차례 뒤에 목표 열이 올 수 있어 열 이름으로 찾는다. 이름이 없는 표는 끝 칸이다.
    header = next((cells_of(line) for line in section.splitlines() if line.strip().startswith("|")), [])
    column = header.index("차례") if "차례" in header else -1
    for cells in table_rows(section):
        number, turn = cells[0], cells[column if column < len(cells) else -1]
        if not turn.startswith("대기:"):
            continue
        for day, clock in WAIT_DATE.findall(turn):
            moment = datetime.fromisoformat(f"{day} {clock or '00:00'}")
            if moment <= now:
                items.append((number, turn))
                break
    return items


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("TASKS.md")
    text = path.read_text(encoding="utf-8")
    due = due_items(text, date.today())
    waits = passed_waits(text, datetime.now())
    if due:
        print("\n밀린 주기적 항목:")
        for task, reason in due:
            print(f"- {task} ({reason})")
    if waits:
        print("\n날짜가 지난 대기 항목:")
        for number, turn in waits:
            print(f"- {number} ({turn})")


if __name__ == "__main__":
    main()
