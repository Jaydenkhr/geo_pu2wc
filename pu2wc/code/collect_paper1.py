#!/usr/bin/env python3
"""
소스지도 인용 수집기 v5
게이트키핑 v2.1 질의구조 + 비용 2중 가드

Usage:
  python collect.py               -- main_v2 본수집 (1순위 auto 본체)
  python collect.py --smoke       -- 스모크 테스트 2질의 × 4엔진 (비용 실측 → 자동 감속)
  python collect.py --priority2   -- 2순위 forced (ChatGPT+Claude)
  python collect.py --priority3   -- 3순위 T3 부속
  python collect.py --priority4   -- 4순위 모델급 (Claude Haiku)
  python collect.py perplexity gemini  -- 특정 엔진만
"""

# ─────────────────────────────────────────────────────────────────
# [공개용 재구성판] 논문1(광고학연구 37(4)) 수집 도구
# 원 스크립트는 논문1 수집(2026-07) 이후 다른 연구에 재사용되며 수정되었다.
# 이 파일은 그 스크립트에서 (1) 모델 식별자를 논문 표 1의 수집 당시 값으로 되돌리고,
# (2) 이후 추가된 응답 메타데이터 저장 필드를 제거한 판이다.
# 요청 파라미터(지시문·검색 도구·토큰 상한)와 수집 절차는 수집 당시와 같다.
# 결과 저장은 Supabase REST(citation_collection 테이블)를 쓴다. 키는 .env.local 환경변수로 읽는다.
# ─────────────────────────────────────────────────────────────────
import os, sys, json, time, re, requests
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv(".env.local")

ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
PERPLEXITY_API_KEY  = os.getenv("PERPLEXITY_API_KEY")
SUPABASE_URL        = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

MAIN_BATCH = "main_v2"

# ── 모델 ──────────────────────────────────────────────────────────
MODELS = {
    "perplexity": "sonar",
    "chatgpt":    "gpt-5.5",          # 반환 스냅샷 gpt-5.5-2026-04-23 (논문 표 1)
    "gemini":     "gemini-3.5-flash",
    "claude":     "claude-sonnet-5",
    "claude_low": "claude-haiku-4-5",
}

# ── 비용 단가 (USD/1M tok 또는 flat) ──────────────────────────────
# Claude Sonnet 5: Anthropic 공식 프로모 단가 $2/$10 per MTok (2026-08-31까지, 정가 $3/$15). 나머지: 추정 (스모크 실측으로 확인)
COST_RATES = {
    "claude":     {"in": 2.0e-6,   "out": 10.0e-6},   # Sonnet 5 프로모 (~08/31)
    "chatgpt":    {"in": 10.0e-6,  "out": 30.0e-6},   # gpt-5.5 추정
    "gemini":     {"in": 0.15e-6,  "out": 0.60e-6},   # gemini-3.5-flash 추정
    "perplexity": {"in": 0.0,      "out": 0.0, "req": 0.001},  # $1/1000 req
}

# ── 비용 가드 (G6) ────────────────────────────────────────────────
COST_CAPS = {
    "claude":     30.0,   # $30 하드캡 (HQ 지시)
    "chatgpt":    15.0,   # $15
    "perplexity":  5.0,   # $5
    "gemini":     None,   # 무료 쿼터 소진 시 오류로 자동 중단
}

# ── 가변 설정 (스모크 후 자동 감속 시 수정) ──────────────────────
_cfg = {
    "n_runs":          5,
    "claude_max_uses": 2,    # G1
    "run_forced":      True, # 2순위 실행 여부
    "run_model_tier":  True, # 4순위 실행 여부
}

# ── 하드캡 누적 비용 추적 (G6) ────────────────────────────────────
_tracker = {eng: {"spent": 0.0, "stopped": False, "consec": 0} for eng in COST_CAPS}


# ─────────────────────────────────────────────────────────────────
# 질의 목록 v5.1 — 41개 (T0×7 T1×14 T2×14 T3×6)
# 근거: 논문1_질의서_v5.1_최종.md. 필드: id·tier·industry·formulation·geo_tags
# geo_tags = GEO-bench {nature/intent/answer_type}
# ─────────────────────────────────────────────────────────────────
def _gt(nature, intent, answer_type):
    return {"nature": nature, "intent": intent, "answer_type": answer_type}

QUERIES_V2 = [
    # ── 전자IT (T3 포함 7) ─ geo_tags는 질의서 표에 명시 ──────────
    {"id": "el_t0",  "tier": "T0", "industry": "전자IT", "formulation": "사실-사업구조", "text": "삼성전자는 주력 사업이 뭐야?",              "geo_tags": _gt("factual","research","fact")},
    {"id": "el_t1a", "tier": "T1", "industry": "전자IT", "formulation": "추천형",       "text": "스마트폰 추천해줘",                        "geo_tags": _gt("opinion","research","list")},
    {"id": "el_t1b", "tier": "T1", "industry": "전자IT", "formulation": "구매조언형",    "text": "냉장고 뭐 사는 게 좋아?",                  "geo_tags": _gt("opinion","research","list")},
    {"id": "el_t2a", "tier": "T2", "industry": "전자IT", "formulation": "장단점형",      "text": "갤럭시 S25 장단점 알려줘",                "geo_tags": _gt("comparison","consideration","list")},
    {"id": "el_t2b", "tier": "T2", "industry": "전자IT", "formulation": "후기형",        "text": "삼성 비스포크 냉장고 실사용 후기 어때?",  "geo_tags": _gt("opinion","consideration","opinion")},
    {"id": "el_t3a", "tier": "T3", "industry": "전자IT", "formulation": "타이밍형",      "text": "갤럭시 S25 지금 사도 돼, 아니면 기다려?", "geo_tags": _gt("advice","purchase","opinion")},
    {"id": "el_t3b", "tier": "T3", "industry": "전자IT", "formulation": "채널형",        "text": "갤럭시 S25 어디서 사는 게 제일 싸?",      "geo_tags": _gt("factual","purchase","fact")},
    # ── 자동차 (T3 포함 7) ──────────────────────────────────────
    {"id": "au_t0",  "tier": "T0", "industry": "자동차", "formulation": "사실-브랜드관계", "text": "현대차그룹에는 어떤 자동차 브랜드들이 있어?", "geo_tags": _gt("factual","research","fact")},
    {"id": "au_t1a", "tier": "T1", "industry": "자동차", "formulation": "추천형",        "text": "전기차 추천해줘",                         "geo_tags": _gt("opinion","research","list")},
    {"id": "au_t1b", "tier": "T1", "industry": "자동차", "formulation": "선호형",        "text": "패밀리 SUV 뭐가 좋아?",                   "geo_tags": _gt("opinion","research","list")},
    {"id": "au_t2a", "tier": "T2", "industry": "자동차", "formulation": "후기형",        "text": "아이오닉5 실제 타는 사람들 평이 어때?",   "geo_tags": _gt("opinion","consideration","opinion")},
    {"id": "au_t2b", "tier": "T2", "industry": "자동차", "formulation": "구매가치형",    "text": "쏘렌토 하이브리드 살만해?",               "geo_tags": _gt("opinion","consideration","opinion")},
    {"id": "au_t3a", "tier": "T3", "industry": "자동차", "formulation": "조언형",        "text": "아이오닉5 살까 말까 고민인데 어떻게 생각해?", "geo_tags": _gt("advice","purchase","opinion")},
    {"id": "au_t3b", "tier": "T3", "industry": "자동차", "formulation": "출시대기형",    "text": "쏘렌토 신형 나온다던데 기다리는 게 나아?", "geo_tags": _gt("advice","purchase","opinion")},
    # ── 금융 (5) ────────────────────────────────────────────────
    {"id": "fi_t0",  "tier": "T0", "industry": "금융", "formulation": "사실-서비스구조", "text": "카카오뱅크는 일반 은행이랑 뭐가 달라?",   "geo_tags": _gt("factual","research","fact")},
    {"id": "fi_t1a", "tier": "T1", "industry": "금융", "formulation": "추천형",         "text": "신용카드 추천해줘",                        "geo_tags": _gt("opinion","research","list")},
    {"id": "fi_t1b", "tier": "T1", "industry": "금융", "formulation": "조건검색형",     "text": "파킹통장 금리 높은 데 어디야?",           "geo_tags": _gt("opinion","research","list")},
    {"id": "fi_t2a", "tier": "T2", "industry": "금융", "formulation": "혜택평가형",     "text": "KB국민카드 혜택 쓸만해?",                 "geo_tags": _gt("opinion","consideration","opinion")},
    {"id": "fi_t2b", "tier": "T2", "industry": "금융", "formulation": "품질확인형",     "text": "카카오뱅크 세이프박스 이자 괜찮아?",      "geo_tags": _gt("opinion","consideration","opinion")},
    # ── 유통 (5) ────────────────────────────────────────────────
    {"id": "re_t0",  "tier": "T0", "industry": "유통", "formulation": "사실-서비스내용", "text": "쿠팡 와우 멤버십 혜택이 정확히 뭐야?",    "geo_tags": _gt("factual","research","fact")},
    {"id": "re_t1a", "tier": "T1", "industry": "유통", "formulation": "조건검색형",     "text": "온라인 장보기 어디가 제일 싸?",           "geo_tags": _gt("opinion","research","list")},
    {"id": "re_t1b", "tier": "T1", "industry": "유통", "formulation": "선호형",         "text": "새벽배송 어디가 좋아?",                   "geo_tags": _gt("opinion","research","list")},
    {"id": "re_t2a", "tier": "T2", "industry": "유통", "formulation": "비교형",         "text": "로켓프레시랑 쓱배송 중에 뭐가 나아?",     "geo_tags": _gt("comparison","consideration","list")},
    {"id": "re_t2b", "tier": "T2", "industry": "유통", "formulation": "구매가치형",     "text": "이마트 트레이더스 갈만해?",               "geo_tags": _gt("opinion","consideration","opinion")},
    # ── 식음료 ★CJ (5) ─────────────────────────────────────────
    {"id": "fo_t0",  "tier": "T0", "industry": "식음료", "formulation": "사실-기업관계", "text": "CJ제일제당이랑 CJ는 무슨 관계야?",        "geo_tags": _gt("factual","research","fact")},
    {"id": "fo_t1a", "tier": "T1", "industry": "식음료", "formulation": "선호형",       "text": "만두는 어느 브랜드가 맛있어?",            "geo_tags": _gt("opinion","research","list")},
    {"id": "fo_t1b", "tier": "T1", "industry": "식음료", "formulation": "추천형",       "text": "간편식 추천해줘",                         "geo_tags": _gt("opinion","research","list")},
    {"id": "fo_t2a", "tier": "T2", "industry": "식음료", "formulation": "품질확인형",   "text": "비비고 만두 맛있어?",                     "geo_tags": _gt("opinion","consideration","opinion")},
    {"id": "fo_t2b", "tier": "T2", "industry": "식음료", "formulation": "구매가치형",   "text": "햇반 컵반 먹을만해?",                     "geo_tags": _gt("opinion","consideration","opinion")},
    # ── 통신 ★SK (T3 포함 7) ───────────────────────────────────
    {"id": "te_t0",  "tier": "T0", "industry": "통신", "formulation": "사실-상품종류",  "text": "SKT 5G 요금제는 종류가 뭐뭐 있어?",       "geo_tags": _gt("factual","research","fact")},
    {"id": "te_t1a", "tier": "T1", "industry": "통신", "formulation": "선호형",         "text": "5G 요금제 어디 통신사가 제일 나아?",      "geo_tags": _gt("opinion","research","list")},
    {"id": "te_t1b", "tier": "T1", "industry": "통신", "formulation": "추천형",         "text": "인터넷 결합상품 추천해줘",                "geo_tags": _gt("opinion","research","list")},
    {"id": "te_t2a", "tier": "T2", "industry": "통신", "formulation": "비교형",         "text": "SKT랑 KT 요금제 중에 뭐가 나아?",         "geo_tags": _gt("comparison","consideration","list")},
    {"id": "te_t2b", "tier": "T2", "industry": "통신", "formulation": "품질확인형",     "text": "KT 인터넷 결합하면 실제로 많이 싸져?",    "geo_tags": _gt("opinion","consideration","opinion")},
    {"id": "te_t3a", "tier": "T3", "industry": "통신", "formulation": "전환형",         "text": "SKT에서 알뜰폰으로 갈아타면 손해야?",     "geo_tags": _gt("advice","purchase","opinion")},
    {"id": "te_t3b", "tier": "T3", "industry": "통신", "formulation": "손익형",         "text": "KT 인터넷 지금 바꾸면 위약금 때문에 손해야?", "geo_tags": _gt("advice","purchase","opinion")},
    # ── 부동산/건설 (5) ────────────────────────────────────────
    {"id": "es_t0",  "tier": "T0", "industry": "부동산", "formulation": "사실-브랜드소속", "text": "래미안은 어느 건설사 브랜드야?",          "geo_tags": _gt("factual","research","fact")},
    {"id": "es_t1a", "tier": "T1", "industry": "부동산", "formulation": "순위형",       "text": "브랜드 아파트 순위가 어떻게 돼?",         "geo_tags": _gt("opinion","research","list")},
    {"id": "es_t1b", "tier": "T1", "industry": "부동산", "formulation": "브랜드군형",     "text": "1군 아파트 브랜드가 어디어디야?",         "geo_tags": _gt("opinion","research","list")},  # v5.1→증빙교체: 원문 '신축 아파트 브랜드 어디가 좋아?'는 증빙미확보(HQ 승인)
    {"id": "es_t2a", "tier": "T2", "industry": "부동산", "formulation": "구매가치형",   "text": "래미안 원베일리 살만해?",                 "geo_tags": _gt("opinion","consideration","opinion")},
    {"id": "es_t2b", "tier": "T2", "industry": "부동산", "formulation": "소문확인형",   "text": "힐스테이트 하자 많다던데 진짜야?",        "geo_tags": _gt("opinion","consideration","opinion")},
]

SMOKE_QUERY_IDS    = {"el_t1a", "el_t2a"}
T3_QUERY_IDS       = {q["id"] for q in QUERIES_V2 if q["tier"] == "T3"}
BASE_QUERY_IDS     = {q["id"] for q in QUERIES_V2 if q["tier"] != "T3"}  # 35개
MODEL_TIER_QUERY_IDS = {
    "el_t1a", "el_t2a", "au_t1a", "au_t2a",
    "fi_t1a", "fi_t2a", "re_t1a", "re_t2a",
    "fo_t1a", "fo_t2a", "te_t1a", "te_t2a",
}  # 산업별 T1·T2 각 1 = 12개

# ── 공식 도메인 매칭표 v2 (질의서 v5.1) ───────────────────────────
# suffix 매칭(등록도메인 기준) + owned_corp / owned_content 2분류.
# 굵게(신규)는 CC 실존·소유 확인 완료분만 편입. 보류: sktuniverse.com, hdc-dev.com(HQ 확인).
OFFICIAL_DOMAINS = {
    "전자IT": [("samsung.com","owned_corp"), ("skhynix.com","owned_corp"),
             ("lge.co.kr","owned_corp"), ("samsungsvc.co.kr","owned_corp")],
    "자동차": [("hyundai.com","owned_corp"), ("kia.com","owned_corp"),
             ("genesis.com","owned_corp"), ("hyundaimotorgroup.com","owned_corp")],
    "금융":   [("kbstar.com","owned_corp"), ("kbfg.com","owned_corp"),
             ("kakaobank.com","owned_corp"), ("kbcard.com","owned_corp"),
             ("kbthink.com","owned_content")],
    "유통":   [("coupang.com","owned_corp"), ("emart.com","owned_corp"),
             ("ssg.com","owned_corp"), ("shinsegae.com","owned_corp")],  # coupang.jobs는 suffix 불일치로 자동 제외
    "식음료": [("cj.net","owned_corp"), ("cjcheiljedang.com","owned_corp"),
             ("nongshim.com","owned_corp"), ("bibigo.com","owned_corp"),
             ("cjthemarket.com","owned_content")],
    "통신":   [("sktelecom.com","owned_corp"), ("tworld.co.kr","owned_corp"),
             ("kt.com","owned_corp"), ("lguplus.com","owned_corp")],
    "부동산": [("raemian.co.kr","owned_corp"), ("xi.co.kr","owned_corp"),
             ("hillstate.co.kr","owned_corp"), ("samsungcnt.com","owned_corp")],
}


# ─────────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────────

def extract_domains(urls: list) -> list:
    seen = set(); result = []
    for url in urls:
        try:
            netloc = urlparse(url).netloc.lower()
            d = netloc[4:] if netloc.startswith("www.") else netloc
            if d and d not in seen:
                seen.add(d); result.append(d)
        except Exception:
            pass
    return result


def extract_urls_from_text(text: str) -> list:
    return list(dict.fromkeys(re.findall(r'https?://[^\s\)"\'<>,\]\["]+', text)))


def safe_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)[:50000]


def resolve_redirect_url(url: str, timeout: int = 10) -> str | None:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CitationCollector/5.0)"}
    for method in ("head", "get"):
        try:
            fn = requests.head if method == "head" else requests.get
            kw = {"allow_redirects": True, "timeout": timeout, "headers": headers}
            if method == "get":
                kw["stream"] = True
            r = fn(url, **kw)
            if method == "get":
                r.close()
            final = r.url
            return None if "vertexaisearch" in final else final
        except Exception:
            continue
    return None


def match_official(domains: list, industry: str) -> tuple[bool, list]:
    """도메인 목록 × 산업 → (official_cited, matched_list).
    v5.1: suffix 매칭(등록도메인 기준) + owned_corp/owned_content 기록.
    matched_list = [{"domain":인용도메인, "official":매칭공식도메인, "owned":owned_corp|owned_content}, ...]
    """
    official_list = OFFICIAL_DOMAINS.get(industry, [])
    if not official_list:
        return False, []
    def _norm(d: str) -> str:
        d = (d or "").lower()
        return d[4:] if d.startswith("www.") else d
    matched = []
    for d in domains:
        nd = _norm(d)
        for od, owned in official_list:
            if nd == od or nd.endswith("." + od):   # suffix 매칭
                matched.append({"domain": d, "official": od, "owned": owned})
                break
    return bool(matched), matched


def _add_cost(engine_key: str, cost: float) -> bool:
    """비용 추가 후 캡 도달 여부 반환 (True면 해당 엔진 중단). G6"""
    t = _tracker.get(engine_key)
    if not t:
        return False
    t["spent"] += cost
    cap = COST_CAPS.get(engine_key)
    if cap is not None and t["spent"] >= cap:
        t["stopped"] = True
        return True
    return False


# ─────────────────────────────────────────────────────────────────
# 엔진별 수집 함수  →  (result_dict, tok_in, tok_out, cost_usd)
# ─────────────────────────────────────────────────────────────────

def collect_perplexity(query_text: str, **_) -> tuple[dict, int, int, float]:
    resp = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"},
        json={"model": MODELS["perplexity"], "messages": [{"role": "user", "content": query_text}]},
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage") or {}
    tok_in  = usage.get("prompt_tokens", 0) or 0
    tok_out = usage.get("completion_tokens", 0) or 0
    cost    = COST_RATES["perplexity"]["req"]
    return ({
        "answer": data["choices"][0]["message"]["content"],
        "urls":   list(data.get("citations") or []),
        "raw":    {"model": data.get("model"), "usage": usage,
                   # 2026-08-05 추가캡처: search_results(url·title·snippet·date). citations와 URL 집합은 동일하나 메타 보존.
                   "search_results": (data.get("search_results") or [])},
        "search_triggered": True,
        "final_urls": None,
    }, tok_in, tok_out, cost)


def _oai_responses_extract(output: list) -> tuple[str, list, bool]:
    """Responses API output → (answer, urls, search_triggered)"""
    answer_parts, urls = [], []
    search_triggered = False
    for item in output:
        t = getattr(item, "type", "")
        if t == "web_search_call":
            search_triggered = True
        elif t == "message":
            for c in (getattr(item, "content", []) or []):
                txt = getattr(c, "text", None)
                if txt:
                    answer_parts.append(txt)
                for ann in (getattr(c, "annotations", []) or []):
                    if getattr(ann, "type", "") == "url_citation":
                        url = getattr(ann, "url", None)
                        if url:
                            urls.append(url)
    return "\n".join(answer_parts), list(dict.fromkeys(urls)), search_triggered


def _collect_openai(query_text: str, forced: bool = False) -> tuple[dict, int, int, float]:
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    # G4: "필요시 최대 2회만 검색" 지시 포함
    if forced:
        instructions = "반드시 웹 검색을 실행한 뒤 최신 정보를 바탕으로 답변하세요. 필요시 최대 2회만 검색하세요. 한국어로 답변하세요."
    else:
        instructions = "검색이 필요하다면 최대 2회까지만 하세요. 한국어로 답변하세요."  # G4
    r = client.responses.create(
        model=MODELS["chatgpt"],
        input=query_text,
        instructions=instructions,
        tools=[{"type": "web_search_preview"}],
        max_output_tokens=8192,  # G3
    )
    answer, urls, search_triggered = _oai_responses_extract(r.output)
    if not urls:
        urls = extract_urls_from_text(answer)
    tok_in  = r.usage.input_tokens
    tok_out = r.usage.output_tokens
    cost    = tok_in * COST_RATES["chatgpt"]["in"] + tok_out * COST_RATES["chatgpt"]["out"]
    return ({
        "answer": answer,
        "urls":   urls,
        "raw":    {"model": r.model, "forced": forced,
                   "output_types": [getattr(o, "type", "?") for o in r.output]},
        "search_triggered": search_triggered,
        "final_urls": None,
    }, tok_in, tok_out, cost)


def collect_openai_auto(query_text: str, **_)   -> tuple[dict, int, int, float]:
    return _collect_openai(query_text, forced=False)


def collect_openai_forced(query_text: str, **_) -> tuple[dict, int, int, float]:
    return _collect_openai(query_text, forced=True)


def collect_gemini(query_text: str, **_) -> tuple[dict, int, int, float]:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=MODELS["gemini"],
        contents=query_text,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )
    answer   = response.text or ""
    raw_urls = []
    for candidate in response.candidates:
        gm = getattr(candidate, "grounding_metadata", None)
        if not gm:
            continue
        for chunk in getattr(gm, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            if web:
                uri = getattr(web, "uri", None)
                if uri:
                    raw_urls.append(uri)
    raw_urls = list(dict.fromkeys(raw_urls))

    final_urls = []
    for url in raw_urls:
        if "vertexaisearch" in url:
            resolved = resolve_redirect_url(url)
            final_urls.append(resolved if resolved else url)
            time.sleep(0.12)
        else:
            final_urls.append(url)
    final_urls = list(dict.fromkeys(final_urls))

    um      = getattr(response, "usage_metadata", None)
    tok_in  = getattr(um, "prompt_token_count", 0) or 0
    tok_out = getattr(um, "candidates_token_count", 0) or 0
    cost    = tok_in * COST_RATES["gemini"]["in"] + tok_out * COST_RATES["gemini"]["out"]
    ok      = sum(1 for u in final_urls if "vertexaisearch" not in u)
    return ({
        "answer": answer,
        "urls":   raw_urls,
        "raw":    {"raw_urls": raw_urls, "resolve_ok": ok, "total": len(raw_urls)},
        "search_triggered": True,
        "final_urls": final_urls,
    }, tok_in, tok_out, cost)


def _collect_claude(query_text: str, forced: bool = False,
                    model_key: str = "claude") -> tuple[dict, int, int, float]:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    max_uses = _cfg["claude_max_uses"]  # G1 — 스모크 후 자동 감속 시 1로 바뀔 수 있음
    model    = MODELS[model_key]

    kwargs: dict = {
        "model":      model,
        "max_tokens": 4096,  # G2
        "tools": [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}],
        "messages": [{"role": "user", "content": query_text}],
    }
    if forced:
        kwargs["system"] = "반드시 웹 검색을 실행한 뒤 최신 정보를 바탕으로 답변하세요."

    response = client.messages.create(**kwargs)

    tok_in  = response.usage.input_tokens
    tok_out = response.usage.output_tokens
    cost    = tok_in * COST_RATES["claude"]["in"] + tok_out * COST_RATES["claude"]["out"]

    answer_parts, urls = [], []
    for block in response.content:
        btype = getattr(block, "type", "")
        if btype == "text":
            answer_parts.append(block.text)
        elif btype == "web_search_tool_result":
            for item in (getattr(block, "content", []) or []):
                url = item.get("url") if isinstance(item, dict) else getattr(item, "url", None)
                if url:
                    urls.append(url)

    answer = "\n".join(answer_parts)
    urls   = list(dict.fromkeys(urls))
    if not urls:
        urls = extract_urls_from_text(answer)

    return ({
        "answer": answer,
        "urls":   urls,
        "raw":    {
            "stop_reason":  response.stop_reason,
            "block_types":  [getattr(b, "type", "?") for b in response.content],
            "model":        model,
            "max_uses":     max_uses,
        },
        "search_triggered": any(
            getattr(b, "type", "") in ("web_search_tool_result", "server_tool_use")
            for b in response.content
        ),
        "final_urls": None,
    }, tok_in, tok_out, cost)


def collect_claude(query_text: str, **_)        -> tuple[dict, int, int, float]:
    return _collect_claude(query_text, forced=False, model_key="claude")


def collect_claude_forced(query_text: str, **_) -> tuple[dict, int, int, float]:
    return _collect_claude(query_text, forced=True, model_key="claude")


def collect_claude_haiku(query_text: str, **_)  -> tuple[dict, int, int, float]:
    return _collect_claude(query_text, forced=False, model_key="claude_low")


# ─────────────────────────────────────────────────────────────────
# 엔진 레지스트리
# ─────────────────────────────────────────────────────────────────
ENGINES = {
    # 1순위 auto 본체
    "perplexity":     {"fn": collect_perplexity,    "mode": "default", "db_engine": "perplexity", "model_tier": "default"},
    "chatgpt":        {"fn": collect_openai_auto,   "mode": "auto",    "db_engine": "chatgpt",    "model_tier": "default"},
    "gemini":         {"fn": collect_gemini,        "mode": "default", "db_engine": "gemini",     "model_tier": "default"},
    "claude":         {"fn": collect_claude,        "mode": "auto",    "db_engine": "claude",     "model_tier": "default"},
    # 2순위 forced
    "chatgpt_forced": {"fn": collect_openai_forced, "mode": "forced",  "db_engine": "chatgpt",    "model_tier": "default"},
    "claude_forced":  {"fn": collect_claude_forced, "mode": "forced",  "db_engine": "claude",     "model_tier": "default"},
    # 4순위 모델급 (Claude Haiku)
    "claude_haiku":   {"fn": collect_claude_haiku,  "mode": "auto",    "db_engine": "claude",     "model_tier": "low"},
}

AUTO_ENGINE_KEYS   = ["perplexity", "chatgpt", "gemini", "claude"]
FORCED_ENGINE_KEYS = ["chatgpt_forced", "claude_forced"]
T3_ENGINE_KEYS     = ["perplexity", "chatgpt", "gemini", "claude"]
HAIKU_ENGINE_KEYS  = ["claude_haiku"]


# ─────────────────────────────────────────────────────────────────
# Supabase
# ─────────────────────────────────────────────────────────────────

def _sb_headers():
    return {
        "apikey":        SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }


def insert_row(row: dict):
    resp = requests.post(f"{SUPABASE_URL}/rest/v1/citation_collection",
                         headers=_sb_headers(), json=row, timeout=30)
    resp.raise_for_status()


def seed_tracker_from_db(batch_label: str):
    """이전 invocation 누적 cost_est를 _tracker에 시딩 → 하드캡을 분할실행 간 누적 적용."""
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/citation_collection"
            f"?batch_label=eq.{batch_label}&error=is.null&select=engine,cost_est",
            headers={"apikey": SUPABASE_SECRET_KEY, "Authorization": f"Bearer {SUPABASE_SECRET_KEY}"},
            timeout=30,
        )
        resp.raise_for_status()
        agg = {}
        for r in resp.json():
            e = r.get("engine"); agg[e] = agg.get(e, 0.0) + (r.get("cost_est") or 0)
        for e, s in agg.items():
            if e in _tracker:
                _tracker[e]["spent"] = s
                cap = COST_CAPS.get(e)
                if cap is not None and s >= cap:
                    _tracker[e]["stopped"] = True
        if agg:
            print("[누적캡 시딩] " + ", ".join(
                f"{e}=${agg.get(e,0):.2f}{'(CAP중단)' if _tracker.get(e,{}).get('stopped') else ''}"
                for e in COST_CAPS if e in agg))
    except Exception as ex:
        print(f"[누적캡 시딩 실패—0에서 시작] {str(ex)[:80]}")


def get_completed_set(batch_label: str) -> set:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/citation_collection"
        f"?batch_label=eq.{batch_label}&error=is.null"
        f"&select=query_id,engine,run_index,search_mode,model_tier",
        headers={"apikey": SUPABASE_SECRET_KEY, "Authorization": f"Bearer {SUPABASE_SECRET_KEY}"},
        timeout=30,
    )
    rows = resp.json()
    return {
        (r["query_id"], r["engine"], r.get("run_index", 1),
         r.get("search_mode") or "", r.get("model_tier") or "default")
        for r in rows
    }


# ─────────────────────────────────────────────────────────────────
# 공통 수집 실행기
# ─────────────────────────────────────────────────────────────────

def run_collection(queries: list, engine_keys: list, batch_label: str,
                   run_index: int = 1, completed_set: set | None = None) -> tuple[int, list]:
    engines = {k: ENGINES[k] for k in engine_keys if k in ENGINES}
    to_run  = []
    for q in queries:
        for ekey, ecfg in engines.items():
            # 하드캡 도달 엔진 건너뜀 (G6)
            if _tracker.get(ecfg["db_engine"], {}).get("stopped"):
                continue
            resume_key = (q["id"], ecfg["db_engine"], run_index,
                          ecfg["mode"], ecfg.get("model_tier", "default"))
            if completed_set and resume_key in completed_set:
                continue
            to_run.append((q, ekey, ecfg))

    skipped = len(queries) * len(engines) - len(to_run) - sum(
        1 for q in queries for ekey, ecfg in engines.items()
        if _tracker.get(ecfg["db_engine"], {}).get("stopped")
    )
    if completed_set and skipped > 0:
        print(f"  [run={run_index}] 재개: 기완료 건너뜀 포함")
    if not to_run:
        print(f"  [run={run_index}] 실행 없음 (전량 완료 또는 캡 도달)")
        return 0, []

    print(f"\n[run={run_index}/{batch_label}] {len(to_run)}회 수집 시작")
    success = 0; fail_log = []

    for i, (q, ekey, ecfg) in enumerate(to_run, 1):
        db_eng = ecfg["db_engine"]

        # G6: 루프 중 캡 도달 확인
        if _tracker.get(db_eng, {}).get("stopped"):
            print(f"  [SKIP] {ekey} — 하드캡 도달, 중단")
            continue

        label = f"[{i:4d}/{len(to_run)}] {ekey:18s} | {q['id']}"
        print(f"  {label}", end=" ... ", flush=True)

        try:
            result, tok_in, tok_out, cost = ecfg["fn"](q["text"])
            urls   = result["urls"]
            final  = result["final_urls"]
            domains = extract_domains(final if final else urls)
            official_cited, official_matched = match_official(domains, q["industry"])

            insert_row({
                "batch_label":       batch_label,
                "query_id":          q["id"],
                "query_text":        q["text"],
                "query_category":    q["industry"],
                "query_type":        q["formulation"],
                "tier":              q["tier"],
                "industry":          q["industry"],
                "geo_tags":          q["geo_tags"],
                "engine":            db_eng,
                "run_index":         run_index,
                "answer_text":       (result["answer"] or "")[:10000],
                "cited_urls":        urls,
                "cited_domains":     domains,
                "citation_count":    len(urls),
                "raw_response":      json.loads(safe_json(result["raw"])),
                "search_mode":       ecfg["mode"],
                "search_triggered":  result["search_triggered"],
                "final_urls":        final,
                "official_cited":    official_cited,
                "official_matched":  official_matched if official_matched else None,
                "model_tier":        ecfg.get("model_tier", "default"),
                "tokens_input":      tok_in,   # G5
                "tokens_output":     tok_out,  # G5
                "cost_est":          round(cost, 6),  # G5
                "error":             None,
            })

            if completed_set is not None:
                completed_set.add((q["id"], db_eng, run_index,
                                   ecfg["mode"], ecfg.get("model_tier", "default")))

            # G6 하드캡 업데이트 + 연속오류 카운터 리셋
            capped = _add_cost(db_eng, cost)
            if db_eng in _tracker:
                _tracker[db_eng]["consec"] = 0

            success += 1
            note = f"인용 {len(urls)}개, ${cost:.4f}"
            if final:
                ok = sum(1 for u in final if "vertexaisearch" not in u)
                note += f", 해석 {ok}/{len(final)}"
            if capped:
                note += f" ★CAP 도달 — {ekey} 중단"
            print(f"OK ({note})")

        except Exception as e:
            err = str(e)[:500]
            fail_log.append({"engine": ekey, "query_id": q["id"], "run": run_index, "error": err})
            print(f"FAIL: {err[:100]}")
            # item4: 쿼터/크레딧 오류 3연속 → 해당 엔진 조기중단 (조용한 반복 금지)
            el = err.lower()
            if any(s in el for s in ("exceeded your current quota", "insufficient_quota",
                                     "credit balance is too low", "credit balance",
                                     "billing_hard_limit_reached", "insufficient_credit")):
                t = _tracker.get(db_eng)
                if t:
                    t["consec"] += 1
                    if t["consec"] >= 3 and not t["stopped"]:
                        t["stopped"] = True
                        print(f"  🛑 [{db_eng}] 쿼터/크레딧 오류 {t['consec']}연속 → 엔진 조기중단(이후 전부 건너뜀)")
            try:
                insert_row({
                    "batch_label": batch_label, "query_id": q["id"],
                    "query_text": q["text"], "query_category": q["industry"],
                    "query_type": q["formulation"], "tier": q["tier"], "industry": q["industry"],
                    "geo_tags": q["geo_tags"],
                    "engine": db_eng, "run_index": run_index,
                    "search_mode": ecfg["mode"],
                    "model_tier": ecfg.get("model_tier", "default"),
                    "error": err,
                })
            except Exception:
                pass

        time.sleep(0.5)

    print(f"  [run={run_index}] 성공 {success}/{len(to_run)}", end="")
    if fail_log:
        print(f", 실패 {len(fail_log)}")
        for f in fail_log[:5]:
            print(f"    ✗ {f['engine']} | {f['query_id']}: {f['error'][:80]}")
    else:
        print()
    return success, fail_log


# ─────────────────────────────────────────────────────────────────
# 스모크 테스트 (0.5단계) — 실측 후 자동 감속
# ─────────────────────────────────────────────────────────────────

def run_smoke_test() -> dict:
    """2질의 × 4엔진 실행 → 비용 실측 → 프로젝션 → 자동 감속 규칙 적용"""
    print("\n" + "━"*60)
    print("0.5단계 스모크 테스트: 2질의 × 4엔진 × run=1")
    print("━"*60)

    smoke_queries = [q for q in QUERIES_V2 if q["id"] in SMOKE_QUERY_IDS]
    completed     = get_completed_set(MAIN_BATCH)

    # 직접 실행하며 엔진별 비용 수집
    engine_smoke_costs: dict[str, list] = {k: [] for k in AUTO_ENGINE_KEYS}

    for q in smoke_queries:
        for ekey in AUTO_ENGINE_KEYS:
            ecfg   = ENGINES[ekey]
            db_eng = ecfg["db_engine"]
            resume_key = (q["id"], db_eng, 1, ecfg["mode"], ecfg.get("model_tier", "default"))
            if resume_key in completed:
                print(f"  [SKIP] {ekey} | {q['id']} — 이미 완료")
                continue
            print(f"  {ekey:16s} | {q['id']} ...", end=" ", flush=True)
            try:
                result, tok_in, tok_out, cost = ecfg["fn"](q["text"])
                urls   = result["urls"]
                final  = result["final_urls"]
                domains = extract_domains(final if final else urls)
                official_cited, official_matched = match_official(domains, q["industry"])
                insert_row({
                    "batch_label": MAIN_BATCH, "query_id": q["id"],
                    "query_text": q["text"], "query_category": q["industry"],
                    "query_type": q["formulation"], "tier": q["tier"], "industry": q["industry"],
                    "geo_tags": q["geo_tags"],
                    "engine": db_eng, "run_index": 1,
                    "answer_text": (result["answer"] or "")[:10000],
                    "cited_urls": urls, "cited_domains": domains,
                    "citation_count": len(urls),
                    "raw_response": json.loads(safe_json(result["raw"])),
                    "search_mode": ecfg["mode"], "search_triggered": result["search_triggered"],
                    "final_urls": final, "official_cited": official_cited,
                    "official_matched": official_matched if official_matched else None,
                    "model_tier": ecfg.get("model_tier", "default"),
                    "tokens_input": tok_in, "tokens_output": tok_out,
                    "cost_est": round(cost, 6), "error": None,
                })
                engine_smoke_costs[ekey].append(cost)
                completed.add(resume_key)
                _add_cost(db_eng, cost)
                print(f"OK (인용 {len(urls)}개, ${cost:.4f}, in={tok_in}tok)")
            except Exception as e:
                print(f"FAIL: {str(e)[:100]}")
            time.sleep(0.5)

    # ── 프로젝션 계산 ──
    n_base   = len(BASE_QUERY_IDS)  # 35
    n_runs   = _cfg["n_runs"]       # 5 (초기)
    print("\n━━ 스모크 비용 프로젝션 (1순위 auto 본체: 35질의 × N=5) ━━")

    proj: dict[str, float] = {}
    for ekey in AUTO_ENGINE_KEYS:
        costs = engine_smoke_costs.get(ekey, [])
        if not costs:
            print(f"  {ekey:16s}: 데이터 없음 (smoke 건너뜀)")
            proj[ekey] = 0.0
            continue
        avg  = sum(costs) / len(costs)
        full = avg * n_base * n_runs
        print(f"  {ekey:16s}: 평균 ${avg:.4f}/질의 → {n_base}×{n_runs} 외삽 = ${full:.2f}")
        proj[ekey] = full

    total_proj = sum(proj.values())
    print(f"  {'합계':16s}: ${total_proj:.2f}")

    # ── 자동 감속 규칙 ──
    print("\n━━ 자동 감속 규칙 적용 ━━")
    slowdown_log = []

    # Claude
    if proj.get("claude", 0) > 25:
        _cfg["n_runs"] = 3
        new_proj = proj["claude"] * 3 / 5
        slowdown_log.append(f"Claude 프로젝션 ${proj['claude']:.2f} > $25 → N=5→N=3 (재추산 ${new_proj:.2f})")
        if new_proj > 25:
            _cfg["claude_max_uses"] = 1
            slowdown_log.append(f"  N=3에도 ${new_proj:.2f} > $25 → max_uses=2→1")
        print(f"  [감속] " + ", ".join(slowdown_log[-2:]))
    else:
        print(f"  Claude 프로젝션 ${proj.get('claude',0):.2f} ≤ $25 → 변경 없음")

    # ChatGPT (claude n_runs 조정 전 기준)
    chatgpt_proj_n = proj.get("chatgpt", 0) * _cfg["n_runs"] / 5
    if proj.get("chatgpt", 0) > 25:
        _cfg["n_runs"] = min(_cfg["n_runs"], 3)
        slowdown_log.append(f"ChatGPT 프로젝션 ${proj['chatgpt']:.2f} > $25 → N=3으로 제한")
        print(f"  [감속] ChatGPT 프로젝션 ${proj['chatgpt']:.2f} > $25 → N=3")
    else:
        print(f"  ChatGPT 프로젝션 ${proj.get('chatgpt',0):.2f} ≤ $25 → 변경 없음")

    # 전체 합계 → 2·4순위 보류
    if total_proj > 60:
        _cfg["run_forced"] = False
        _cfg["run_model_tier"] = False
        slowdown_log.append(f"전체 ${total_proj:.2f} > $60 → 2순위(forced)·4순위(모델급) 보류")
        print(f"  [보류] 전체 ${total_proj:.2f} > $60 → 2·4순위 보류")
    else:
        print(f"  전체 ${total_proj:.2f} ≤ $60 → 2·4순위 예정대로 진행")

    # ── 최종 설정 출력 ──
    print("\n━━ 스모크 완료 후 적용 설정 ━━")
    print(f"  n_runs:          {_cfg['n_runs']}")
    print(f"  claude_max_uses: {_cfg['claude_max_uses']}  (G1)")
    print(f"  run_forced:      {_cfg['run_forced']}   (2순위)")
    print(f"  run_model_tier:  {_cfg['run_model_tier']}   (4순위)")
    print("━"*60)

    return {"proj": proj, "total_proj": total_proj, "slowdown": slowdown_log}


# ─────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    seed_tracker_from_db(MAIN_BATCH)   # 누적 하드캡 시딩 (분할실행 대비)

    # ── 스모크 테스트 단독 실행 ──────────────────────────────────
    if "--smoke" in args:
        run_smoke_test()
        print("\n[스모크 완료] 본수집을 계속하려면 python collect.py 실행")
        return

    # ── 2순위 forced 단독 ────────────────────────────────────────
    if "--priority2" in args:
        if os.path.exists(".hold_priority24"):
            print("[2순위 forced] ⏸ 보류 (.hold_priority24 — 스모크 자동감속 총액 $60초과 홀드, HQ 확인 대기). 건너뜀.")
            return
        queries   = [q for q in QUERIES_V2 if q["id"] in BASE_QUERY_IDS]
        completed = get_completed_set(MAIN_BATCH)
        n_runs    = _cfg["n_runs"]
        print(f"[2순위 forced] {len(queries)}질의 × {len(FORCED_ENGINE_KEYS)}엔진 × N={n_runs}")
        for run in range(1, n_runs + 1):
            run_collection(queries, FORCED_ENGINE_KEYS, MAIN_BATCH, run, completed)
        return

    # ── 3순위 T3 부속 ────────────────────────────────────────────
    if "--priority3" in args:
        queries   = [q for q in QUERIES_V2 if q["id"] in T3_QUERY_IDS]
        completed = get_completed_set(MAIN_BATCH)
        n_runs    = 3  # T3는 N=3 고정
        print(f"[3순위 T3] {len(queries)}질의 × {len(T3_ENGINE_KEYS)}엔진 × N={n_runs}")
        for run in range(1, n_runs + 1):
            run_collection(queries, T3_ENGINE_KEYS, MAIN_BATCH, run, completed)
        return

    # ── 4순위 모델급 ─────────────────────────────────────────────
    if "--priority4" in args:
        if os.path.exists(".hold_priority24"):
            print("[4순위 Haiku] ⏸ 보류 (.hold_priority24 — 스모크 자동감속 총액 $60초과 홀드, HQ 확인 대기). 건너뜀.")
            return
        queries   = [q for q in QUERIES_V2 if q["id"] in MODEL_TIER_QUERY_IDS]
        completed = get_completed_set(MAIN_BATCH)
        n_runs    = 3  # 모델급 N=3 고정
        print(f"[4순위 모델급 Haiku] {len(queries)}질의 × N={n_runs}")
        for run in range(1, n_runs + 1):
            run_collection(queries, HAIKU_ENGINE_KEYS, MAIN_BATCH, run, completed)
        return

    # ── 1순위 auto 본체 본수집 ───────────────────────────────────
    queries      = [q for q in QUERIES_V2 if q["id"] in BASE_QUERY_IDS]  # 35개
    engine_filter = {a for a in args if not a.startswith("--")}
    engine_keys  = [k for k in AUTO_ENGINE_KEYS if not engine_filter or k in engine_filter]

    # 스모크 테스트 자동 실행 (아직 아무 데이터도 없을 때만)
    completed = get_completed_set(MAIN_BATCH)
    if not completed:
        print("[스모크 테스트 자동 실행 — DB에 데이터 없음]")
        run_smoke_test()
        completed = get_completed_set(MAIN_BATCH)

    n_runs = _cfg["n_runs"]
    target = len(queries) * len(engine_keys) * n_runs
    print(f"\n[1순위 본수집] batch={MAIN_BATCH}, {len(queries)}질의 × {len(engine_keys)}엔진 × N={n_runs} = 목표 {target}건")
    print(f"[재개] 기완료 {len(completed)}건 건너뜀")

    for run in range(1, n_runs + 1):
        run_collection(queries, engine_keys, MAIN_BATCH, run, completed)

    print(f"\n[1순위 완료] batch={MAIN_BATCH}")

    # 하드캡 도달 엔진 보고
    capped = [eng for eng, t in _tracker.items() if t["stopped"]]
    if capped:
        print(f"[비용 가드] 하드캡 도달로 중단된 엔진: {', '.join(capped)}")
        for eng in capped:
            print(f"  {eng}: 누적 ${_tracker[eng]['spent']:.4f} (캡 ${COST_CAPS[eng]})")


if __name__ == "__main__":
    main()
