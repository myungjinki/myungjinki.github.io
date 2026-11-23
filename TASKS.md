# TASKS

## 일회성

이 저장소의 티커는 PMGI다. 일회성 할 일은 이 저장소의 GitHub Issues에 있고, 아래 표는 그 사본이다. 이슈 형식, 일 하나가 잡혀서 끝나기까지, 도구마다 읽고 쓰는 것은 [할 일 기록 흐름](https://github.com/myungjinki/role-ai-engineer/blob/main/docs/task-issues.md)을 따른다.

할 일은 [scripts/tasks.py](scripts/tasks.py)로만 고친다. 이 표와 [STATE.md](STATE.md) '진행 중' 표, [LANDED.md](LANDED.md)는 주 폴더(처음 clone한 폴더)에서 `python3 scripts/tasks.py sync`가 이슈에 맞춰 다시 쓴다. sync는 주 폴더가 기본 브랜치에 있고 `origin/<기본 브랜치>`보다 뒤처지지 않았을 때만 쓰고, 뒤처졌으면 멈춘다(`sync --pull`은 `git pull --ff-only`로 받고 쓴다). worktree에서는 이 세 파일을 고치지 않는다.

- 새 할 일: `tasks.py add --title "<짧은 제목>" --kind <구분> --grade <등급> "<할 일>"`. '할 일'에는 무엇이 되면 끝인지까지 적는다. 새 번호는 이슈 번호에 [scripts/tasks.json](scripts/tasks.json)의 `offset`을 더한 값이라 따로 세지 않는다. 번호 사이가 비어도 지운 번호는 다시 쓰지 않는다.
- 표에서 위에 있는 항목이 먼저다. 잡기: `tasks.py claim PMGI-n --who <도구>-<모델>-<폴더>`. '진행 중'에 있는 일은 다른 세션이 잡지 않는다. 같은 일을 여러 세션이 동시에 잡으면 먼저 잡은 세션이 하고, 진 세션은 그 일을 하지 않는다. 멈추면 `tasks.py note PMGI-n --stopped "<멈춘 곳>" --next "<다음 걸음>"`, 손을 떼면 `tasks.py release PMGI-n`.
- 끝내기: 커밋 메시지 끝에 `(PMGI-n)`을 붙이고 PR 본문에 `Closes #이슈번호`를 넣어 ship한다. 머지되면 바로 `tasks.py close PMGI-n --model "<모델>" --summary "<LANDED에 적을 한 문장>"`으로 닫는 댓글을 남긴다. `Closes`가 이미 닫은 이슈면 댓글만 단다. STATE '지금'에 반영할 것이 있으면 `--now`에 적는다. 머지와 `close` 사이에 sync가 돌아 LANDED에 `(요약 없음, 이슈 #n)` 행이 생겨도, 댓글이 달린 뒤의 sync가 그 행을 고치고 `--now`를 다시 보인다. PR 없이 끝낸 일은 `close`만 한다.
- 고치기: `tasks.py edit PMGI-n`에 `--title`·`--text`·`--kind`·`--order` 중 바꿀 것만 준다. 등급·차례는 `turn`으로 바꾼다.
- 취소: `tasks.py cancel PMGI-n --reason "<취소 이유>"`. 잘못 닫았으면 `tasks.py reopen PMGI-n --reason "<이유>"`로 다시 열고, 주 폴더의 sync가 LANDED에서 그 행을 뺀다.
- 할 일 이슈는 제목이 `PMGI-n`으로 시작하거나 `구분:`·`등급:`·`차례:` 라벨이 있는 이슈다. 버그 신고처럼 둘 다 없는 이슈는 표에 넣지 않고 제목도 바꾸지 않는다. 휴대폰 등에서 만든 이슈를 할 일로 삼으려면 `tasks.py turn #이슈번호 AI`로 차례 라벨을 단다.
- 실패: `tasks.py fail PMGI-n --what "<무엇이 왜 실패했나>"`. 막을 때까지 세션 시작 출력·`show`·`sync`가 보인다. 막았으면 `tasks.py fixed PMGI-n --how "<테스트 이름·검사·함정 줄·커밋>"`.

사용자가 바로 시킨 일은 이번 세션에 끝내면 이슈를 만들지 않고 커밋만 한다. 끝내지 못하면 이슈로 올린다.

차례: `AI`는 AI가 바로 할 수 있는 일, `사용자`는 사용자의 결정이나 행동을 기다리는 일, `대기: 조건`은 조건이 채워져야 시작하는 일이다. 미루거나 사용자 답을 기다리면 `tasks.py turn PMGI-n 사용자`(또는 `AI`, `"대기: 조건"`)로 차례를 고친다.

등급: 맡길 모델 등급(`최상`·`상`·`중`·`하`)이다. 고르는 기준과 등급별 모델은 [AI 사용 전략](https://github.com/myungjinki/role-ai-engineer/blob/main/docs/ai-strategy.md#모델-배정)을 따르고, `사용자` 차례인 항목은 `-`로 둔다.

<!-- tasks.py:일회성 시작. 이 표는 GitHub Issues의 사본이다. 고치지 말고 scripts/tasks.py를 쓴다. -->

| 번호 | 구분 | 할 일 | 등급 | 차례 |
|---|---|---|---|---|
| PMGI-1 | 정리 | 옛 정적 사이트 `docs/`를 지울지 남길지 정하고, 정한 대로 `docs/`와 README '구성'의 설명을 맞추면 끝 (사용자 확인: `docs/` 삭제 여부 결정) 순서: 10 사용자 답(2026-11-23): 옛 정적 사이트 docs/를 지운다(Pages는 gh-pages 브랜치에서 서비스한다). README '구성'의 설명도 맞춘다. | - | AI |
| PMGI-2 | 문서 | 사이트의 목표·범위·완료 기준을 정해 `docs/plan.md`에 적고 README '문서'에서 가리키면 끝 (사용자 확인: 목표·범위 결정 (`docs/` 위치는 PMGI-1 뒤)) 순서: 20 사용자 답(2026-11-23): 이 사이트는 개인 기술 블로그다. README 첫 단락과 docs/plan.md의 목표·범위·완료 기준을 개인 기술 블로그 기준으로 쓴다. 구체 범위(글 주제·발행 주기 등)가 문서로 정해지지 않은 부분은 '정할 것'에 남긴다. | - | AI |

<!-- tasks.py:일회성 끝 -->

## 주기적

번호를 붙이지 않고, 끝나도 지우지 않고 '마지막' 날짜만 고친다.

| 할 일 | 주기 | 마지막 |
|---|---|---|
| README 점검 | 매월 | 2026-11-20 |
