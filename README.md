# myungjinki.github.io

방문자가 myungjinki의 웹 프로젝트를 한곳에서 찾아볼 수 있는 GitHub Pages 개인 사이트다. React와 TypeScript로 만들고 `gh-pages` 브랜치로 배포하며, 주소는 <https://myungjinki.github.io/>다.

지금 상태는 [STATE.md](STATE.md), 할 일은 [TASKS.md](TASKS.md)에 있다.

## 시작하기

필요한 도구: Node.js와 npm. 배포하려면 이 저장소에 푸시할 권한이 있어야 한다.

1. 저장소를 받고 폴더로 이동한다.

   ```bash
   git clone git@github.com:myungjinki/myungjinki.github.io.git
   ```

   ```bash
   cd myungjinki.github.io
   ```

2. 의존성을 설치한다.

   ```bash
   npm install
   ```

3. 개발 서버를 띄운다. <http://localhost:3000>에 프로젝트 목록이 있는 첫 화면이 열리면 정상이다.

   ```bash
   npm start
   ```

## 사용법

가장 자주 하는 일은 첫 화면의 프로젝트 목록에 프로젝트를 더하는 것이다.

1. [src/routes/Home.tsx](src/routes/Home.tsx)의 `Project` 안에 새 프로젝트 링크를 더한다.

   ```tsx
   <a href="https://myungjinki.github.io/my-project/">
     3. My Project
   </a>
   ```

2. `npm start`로 개발 서버를 띄워 <http://localhost:3000> 목록에 `3. My Project` 링크가 보이고 클릭 시 해당 주소로 이동하는지 확인한다.
3. 배포한다. `build/`를 만들어 `gh-pages` 브랜치에 올리며, 몇 분 뒤 <https://myungjinki.github.io/>에 반영된다.

   ```bash
   npm run deploy
   ```

## 확인 방법

아래 명령이 오류 없이 끝나고 `build/index.html`이 생기면 통과다. 에이전트가 따르는 검증 절차는 [AGENTS.md](AGENTS.md#검증)에 있다.

```bash
npm run build
```

## 구성

| 항목 | 쓰는 것 |
|---|---|
| 환경 | Create React App(Webpack·Babel 포함) |
| 언어 | TypeScript |
| UI | React |
| CSS | styled-components, Pico CSS(`public/index.html`에서 CDN으로 불러온다) |
| 라우터 | React Router |
| 배포 | gh-pages |

`docs/`는 지금 배포에 쓰지 않는 옛 정적 HTML 사이트다.

## 문서

- [작업 지침](AGENTS.md): 에이전트가 따르는 검증·커밋 규칙과 함정
- [변경 기록](LANDED.md): 끝나거나 취소한 할 일
