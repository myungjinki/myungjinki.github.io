#!/usr/bin/env python3
"""할 일 도구의 짧은 실행 파일. 이 파일과 이름이 같은 본체를 설치된 jk-template에서 찾아 그대로 실행한다.

tasks.py, overdue.py, check-task-files.py의 내용이 같다. 고치지 말고 install_tasks.py로 놓는다.
본체의 판은 jk-template이 정한 stable이다. 이 저장소만 다른 판을 쓰려면 scripts/tasks.json에 "version": "0.66.0"처럼 적는다.
환경 변수 JK_TASKS_HOME(jk-template의 shared/scripts 경로)과 JK_TASKS_VERSION은 설치본과 tasks.json보다 앞선다.
"""
import json
import os
from pathlib import Path
import re
import sys

# install_tasks.py와 세션 시작 훅이 읽는 이 실행 파일의 판
TASKS_SCRIPT_VERSION = 8


def _read(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _stop(why):
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    raise SystemExit(
        f"{Path(__file__).name}: 실행하지 않았다. {why}\n"
        "설치(jk-plugins 마켓플레이스를 먼저 등록한다): Claude는 `claude plugin install jk-template@jk-plugins`, "
        "Codex는 `codex plugin add jk-template@jk-plugins`.\n"
        "갱신: Claude는 `claude plugin marketplace update jk-plugins` 뒤 `claude plugin update jk-template@jk-plugins`, "
        "Codex는 위 설치 명령.\n"
        "설치하지 않고 쓰려면 JK_TASKS_HOME에 jk-template의 shared/scripts 경로를 준다.")


def _installed():
    """Return the plugin folders installed on this device, the newest version first."""
    home = Path.home()
    claude = os.environ.get("CLAUDE_CODE_PLUGIN_CACHE_DIR")
    claude = Path(claude) if claude else Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude") / "plugins"
    records = (_read(claude.expanduser() / "installed_plugins.json").get("plugins") or {}).get("jk-template@jk-plugins")
    found = [Path(record["installPath"]) for record in records or [] if record.get("installPath")]
    codex = Path(os.environ.get("CODEX_HOME") or home / ".codex").expanduser()
    found += (codex / "plugins/cache/jk-plugins/jk-template").glob("*")
    found.append(home / ".gemini/config/plugins/jk-template")

    def version(root):
        return [int(n) for n in re.findall(r"\d+", str(_read(root / ".claude-plugin/plugin.json").get("version")))]
    return sorted((root for root in found if root.is_dir()), key=version, reverse=True)


def _body():
    here = Path(__file__).resolve().parent
    if os.environ.get("JK_TASKS_HOME"):
        homes = [Path(os.environ["JK_TASKS_HOME"]).expanduser()]
    else:
        # jk-template 패키지 자신이나 그 원본 저장소면 설치본보다 먼저 쓴다.
        own = [home for home in (here, here.parent / "plugins/jk-template/shared/scripts") if (home / "releases").is_dir()]
        homes = own[:1] or [root / "shared/scripts" for root in _installed()]
    homes = [home for home in homes if (home / "releases/releases.json").is_file()]
    if not homes:
        _stop("본체가 든 jk-template을 찾지 못했다(Claude·Codex·Antigravity 설치본, JK_TASKS_HOME). "
              "설치본이 있으면 0.66.0보다 오래됐다.")
    wanted = os.environ.get("JK_TASKS_VERSION")
    if not wanted:
        wanted = _read(here / "tasks.json").get("version")
        if wanted is not None and not re.fullmatch(r"\d+\.\d+\.\d+", str(wanted)):
            _stop(f'scripts/tasks.json의 version은 "0.66.0" 같은 판이다: {wanted}')
    for home in homes:
        version = wanted or _read(home / "releases/releases.json").get("stable")
        path = home / "releases" / str(version) / Path(__file__).name
        if path.is_file():
            return path
    have = sorted({path.name for home in homes for path in (home / "releases").iterdir() if path.name[:1].isdigit()})
    _stop(f"{wanted or 'stable'} 판의 본체가 설치된 jk-template에 없다(있는 판: {', '.join(have) or '없음'}). "
          "jk-template을 갱신하거나 scripts/tasks.json의 version을 있는 판으로 바꾸거나 지운다.")


_path = _body()
__file__ = str(_path)
# 본체를 이 모듈 안에서 실행해, 명령으로 실행할 때와 import할 때(ship, 테스트) 모두 사본이 있던 때와 같게 동작한다.
exec(compile(_path.read_bytes(), __file__, "exec", dont_inherit=True), globals())
