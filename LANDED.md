# LANDED

[TASKS.md](TASKS.md)에서 끝나거나 취소한 할 일의 기록이다. 최신이 위로 오게 한 줄씩 더하고, 번호와 완료 내용이나 취소 이유를 한 문장으로 적는다. 주 폴더의 `python3 scripts/tasks.py sync`가 닫힌 이슈를 맨 위에 더하고, '바뀐 것'과 `모델`은 이슈를 닫을 때 남긴 댓글(`tasks.py close`·`cancel`)에서 가져온다. 닫는 댓글보다 sync가 먼저 돌아 `(요약 없음, 이슈 #n)`으로 적힌 행은 댓글이 달린 뒤의 sync가 고친다. `모델`에는 그 일을 실제로 끝낸 모델 이름을 적고, 사람이 끝냈거나 취소했거나 모르면 `-`를 적는다. 번호 없는 일과 상태 변경은 적지 않는다. 그 기록은 커밋에 있고 지금 상태는 [STATE.md](STATE.md)에 있다.

| 번호 | 날짜 | 바뀐 것 | 모델 | 이슈 |
|---|---|---|---|---|
| PMGI-15 | 2026-11-24 | scripts/tasks.py를 공통본 v3로 갱신하고 --diff 무차이, 훅·show·check 검증 통과 | Haiku 5.5 | [#13](https://github.com/myungjinki/myungjinki.github.io/issues/13) |
| PMGI-1 | 2026-11-23 | 옛 정적 사이트 docs/를 삭제하고 README·AGENTS의 docs/ 설명을 지웠다 | claude-haiku-5-5 | [#9](https://github.com/myungjinki/myungjinki.github.io/issues/9) |
| PMGI-7 | 2026-11-19 | `AGENTS.md` '할 일'에 `등급`과 세션 모델 등급을 비교해 '맡기는 법'을 따르는 줄을 합쳤다 | Sonnet 5.5 | - |
| PMGI-6 | 2026-11-19 | `TASKS.md`에 `등급` 열과 머리말 줄을, `LANDED.md`에 `모델` 열과 머리말 설명을 더했다 | Sonnet 5.5 | - |
| PMGI-3 | 2026-11-19 | `package.json` `homepage`와 `src/routes/Home.tsx`의 주소를 옛 계정 `myungjinki91.github.io`에서 `myungjinki.github.io`로 바꿨다 | - | - |
| PMGI-5 | 2026-11-19 | 할 일 번호를 `T-n`에서 티커를 붙인 `PMGI-n`으로 바꿨다 | - | - |
| PMGI-4 | 2026-11-16 | `AGENTS.md` '정해 둔 것'에서 푸시하지 않는다는 규칙을 지웠다 | - | - |
| - | 2026-11-12 | `AGENTS.md`·`TASKS.md`·`STATE.md`를 만들었다 | - | - |
