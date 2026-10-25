# 코드북: 도메인 유형 분류 12유형

분류 함수 `classify_domain()` (analyze_v4.py 인라인)의 판정 규칙을 사람이 읽을 수 있는 형태로 기술.
각 도메인은 아래 12개 유형 중 **하나**로 분류 (상호 배타적).

## 판정 우선순위 (충돌 시 위쪽 유형 우선)

| 순위 | 유형 코드 | 한국어 명칭 | 설명 및 예시 도메인 |
|---:|---------|----------|------------------|
| 1 | `redirect` | 리다이렉트 | Google Vertex AI 검색 프록시 URL. `vertexaisearch.cloud.google.com` 포함 |
| 2 | `video` | 동영상 | 영상 스트리밍 플랫폼. `youtube.com`, `m.youtube.com`, `youtu.be`, `vimeo.com`, `dailymotion.com` |
| 3 | `wiki` | 위키 | 백과사전·위키 플랫폼. `namu.wiki`, `wikipedia.org`, `ko.wikipedia.org`, `en.wikipedia.org`, `wikitree.com`, `fandom.com` |
| 4 | `blog` | 블로그 | 개인·브랜드 블로그. `*.tistory.com`, `blog.naver.com`, `m.blog.naver.com`, `post.naver.com`, `brunch.co.kr`, `medium.com`, `egloos.com` |
| 5 | `fintech` | 핀테크 | 금융 비교·분석 플랫폼. `banksalad.com`, `tossbank.com`, `toss.im`, `card-gorilla.com`, `a-ha.io`, `kr.investing.com` |
| 6 | `review` | 비교리뷰 | 제품·서비스 비교·리뷰 사이트. `ajd.co.kr`, `web.getcha.kr`, `m.kbchachacha.com`, `auto.danawa.com`, `plan.danawa.com` |
| 7 | `community` | 커뮤니티 | 온라인 커뮤니티·포럼·SNS. `dcinside.com`, `clien.net`, `fmkorea.com`, `reddit.com`, `café.naver.com`, `instagram.com`, `teamblind.com` |
| 8 | `academic` | 학술 | 학술 DB·대학·연구기관. `riss.kr`, `dbpia.co.kr`, `kci.go.kr`, `*.ac.kr`, `*.edu`, `scholar.google.com`, `ssrn.com` |
| 9 | `gov` | 정부공공 | 정부·공공기관·협회. `*.go.kr`, `*.or.kr`, `*.re.kr`, `korea.kr`, `kita.net` |
| 10 | `news` | 언론 | 뉴스 미디어·포털 뉴스. `hankyung.com`, `mk.co.kr`, `chosun.com`, `v.daum.net`, `news.naver.com`, `yna.co.kr`, `kbs.co.kr` 등 |
| 11 | `commerce` | 상거래 | 전자상거래·쇼핑몰. `coupang.com`, `gmarket.co.kr`, `danawa.com`, `nosearch.com`, `moyoplan.com`, `amazon.com` |
| 12 | `official` | 공식 | 기업 공식 사이트(명시 목록). `samsung.com`, `apple.com`, `hyundai.com`, `kt.com`, `kb.co.kr` 등 브랜드 직접 도메인 |
| *(기본값)* | `etc` | 기타 | 위 11개에 해당하지 않는 도메인 |

## 판정 기준 상세

### 수프도메인 규칙
- `www.` 접두어는 제거 후 판정 (예: `www.youtube.com` → `youtube.com`)
- `*.tistory.com` 모든 서브도메인 → `blog`
- `*.yna.co.kr` → `news`
- `*.ac.kr`, `*.edu` → `academic`
- `*.go.kr`, `*.or.kr`, `*.re.kr` → `gov`

### 유의사항
- `fintech`와 `review`는 `community`보다 우선 (핀테크·비교리뷰 사이트는 커뮤니티가 아님)
- `official`은 명시 목록에 있을 때만 — 목록에 없는 기업 도메인은 `etc`
- 뉴스 포털(예: `v.daum.net`, `news.naver.com`)은 포털 경유 뉴스이지만 `news` 분류
- `redirect` 유형은 분석에서 제외 처리 가능 (중간 프록시 URL)

## 판정 예시

| 도메인 | 유형 | 이유 |
|--------|------|------|
| namu.wiki | wiki | 위키 목록 직접 매칭 |
| blog.naver.com | blog | 블로그 목록 직접 매칭 |
| v.daum.net | news | 뉴스 목록 직접 매칭 (포털 경유 뉴스) |
| ajd.co.kr | review | 비교리뷰 목록 직접 매칭 |
| banksalad.com | fintech | 핀테크 목록 직접 매칭 |
| samsung.com | official | 공식 목록 직접 매칭 |
| riss.kr | academic | 학술 목록 직접 매칭 |
| fss.or.kr | gov | `.or.kr` 접미어 |
| product.kt.com | etc | official 목록 미포함(kt.com은 포함, product.kt.com은 미포함) |
| edmunds.com | etc | 어느 목록에도 해당 없음 |


## v7.2 분류 각주 (2026-07-18 최종 확정 — 논문·코드북 공용)

**각주 A (해외 종합언론)**: 해외 종합 보도매체(The Guardian, NBC News, Yahoo Tech, AP News, Forbes, 총 5개 매체 11건)는 국내 등록 언론에 준하는 보도 주체로 보아 earned로 분류하였다.

**각주 B (owned 확장)**: 사전 등록한 공식 도메인 목록 외에, 운영 주체가 질의 대상 브랜드로 확인되는 자사 도메인(채용 사이트, 해외법인, 그룹 뉴스룸, 캠페인 도메인, 등록 도메인의 서브도메인 등 14개 도메인 27건, 전체 인용의 0.79%)을 채널 분류(축2)에서 owned로 편입하였다. 다만 응답 단위 공식 인용률(H1)은 사전 등록 목록 기준을 유지하였으며, 확장 정의를 적용한 민감도 검정 결과는 각주/부록에 제시한다.

**각주 C (잔여 미분류)**: 자동 분류 후 잔여 미분류(etc) 도메인 전체(333개)는 연구자가 개별 수동 검수하였으며, 최종 etc(202건, 5.9%)는 검수 후에도 운영 주체를 특정할 수 없는 도메인이다.

**방법 각주 (문형 동등성)**: 수동 검수 확정은 본 분석 표본에만 적용되므로, 문형 동등성 비교는 동일 규칙의 자동 분류 기준으로 산출하였다(최대 편차 2.5%p).
