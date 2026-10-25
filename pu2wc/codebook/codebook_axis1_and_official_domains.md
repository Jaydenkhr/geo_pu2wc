# 부록 C: 도메인 분류 코드북 및 공식도메인 매칭표
## C.1 도메인 유형 분류 (classify_domain 함수 규칙)
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

---
## C.2 산업별 공식 도메인 매칭표 (OFFICIAL_DOMAINS)

> `match_official(domains, industry)` 함수에서 suffix 매칭으로 사용.
> `owned_corp`: 기업 공식 채널 / `owned_content`: 기업 소유 콘텐츠 채널

### 전자IT
| 도메인 패턴 | 소유 유형 |
|---|---|
| samsungsvc.co.kr | owned_corp |

### 자동차
| 도메인 패턴 | 소유 유형 |
|---|---|
| hyundaimotorgroup.com | owned_corp |

### 금융
| 도메인 패턴 | 소유 유형 |
|---|---|
| kbthink.com | owned_content |

### 유통
| 도메인 패턴 | 소유 유형 |
|---|---|
| shinsegae.com | owned_corp |

### 식음료
| 도메인 패턴 | 소유 유형 |
|---|---|
| cjthemarket.com | owned_content |

### 통신
| 도메인 패턴 | 소유 유형 |
|---|---|
| lguplus.com | owned_corp |

### 부동산
| 도메인 패턴 | 소유 유형 |
|---|---|
| samsungcnt.com | owned_corp |

