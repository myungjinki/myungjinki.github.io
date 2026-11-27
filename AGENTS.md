# myungjinki.github.io

모든 저장소의 공통 작업 기준은 '공통 규칙' 구역의 방법으로 읽고, ‘프로젝트 작업 기준’은 이 저장소에 적용한다.

## 공통 규칙

- 일을 시작하기 전에 공통 규칙을 읽는다. 시작 훅이 보인 공통 규칙 문서가 없으면 `python3 scripts/tasks.py rules`를 실행해 끝까지 읽는다. 읽지 못하면 첫 응답에서 알린다.

## 검증

- 코드를 바꿨으면 `npm run build`가 오류 없이 끝나고 `build/index.html`이 생긴다.
- 화면을 바꿨으면 `npm start`로 띄운 <http://localhost:3000>에서 바뀐 화면이 정상 렌더링되고 브라우저 콘솔 오류가 없는지 확인한다.
- 문서만 바꿨으면 상대 링크와 백틱 속 경로를 `git ls-files`와 대조해 없는 경로가 없는지 확인한다.

## 문서

- 목표·범위·완료 기준을 정하면 문서로 적고 README의 '문서' 목록에서 가리킨다.

## 테스트

- 위치: Create React App 관례대로 `src/` 안의 `*.test.tsx`. 아직 테스트가 없어서 `npm test`는 검증에 쓰지 않는다.

## 함정

- `build/`는 `.gitignore`에 있어 커밋하지 않는다. `npm run deploy`가 만들어 `gh-pages` 브랜치에 올린다.

## 프로젝트 작업 기준

- 목적과 사용 대상은 [README.md](README.md)를 따른다. 목표·범위·완료 기준은 아직 정하지 않았다([myungjinki.github.io#10](https://github.com/myungjinki/myungjinki.github.io/issues/10)).
- 요청이 사이트의 목적이나 범위(블로그 추가, 프레임워크 교체 등)를 바꾸면 시작하기 전에 사용자에게 확인받고, 변경 이유와 새 완료 기준을 [myungjinki.github.io#10](https://github.com/myungjinki/myungjinki.github.io/issues/10)의 문서에 적는다.
- 구현 규칙: 화면은 `src/routes/`, 공용 컴포넌트는 `src/components/`에 두고, 스타일은 styled-components로 쓴다.
- 스스로 정하는 일: 코드·문서 수정, 검증, 커밋. 사용자에게 확인받는 일: `npm run deploy`, 의존성 추가·업그레이드, 파일·폴더 삭제.
