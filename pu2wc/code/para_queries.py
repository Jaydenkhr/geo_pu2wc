#!/usr/bin/env python3
"""
2차 웨이브 패러프레이즈 41 정의 + 원문 대조 검수 (수집 아님, 정의/검증 전용).
- 지시서 §2 표 그대로 이식. query_id = 원문 id + '_p'. tier/industry/공식도메인 = 원문과 동일 키.
- 실행: python3 para_queries.py  → 원문 일치 검수 결과만 출력(LLM·DB·수집 0).
"""
import collect

# (원문id, 지시서에 적힌 원문, 변형)
PARA = [
 ("el_t0",  "삼성전자는 주력 사업이 뭐야?",                    "삼성전자는 무슨 사업으로 돈 버는 회사야?"),
 ("el_t1a", "스마트폰 추천해줘",                               "요즘 살만한 스마트폰 뭐가 있어?"),
 ("el_t1b", "냉장고 뭐 사는 게 좋아?",                         "냉장고 추천 좀 해줘"),
 ("el_t2a", "갤럭시 S25 장단점 알려줘",                        "갤럭시 S25 좋은 점이랑 아쉬운 점이 뭐야?"),
 ("el_t2b", "삼성 비스포크 냉장고 실사용 후기 어때?",          "삼성 비스포크 냉장고 써본 사람들 반응 어때?"),
 ("el_t3a", "갤럭시 S25 지금 사도 돼, 아니면 기다려?",         "갤럭시 S25 지금 사는 게 맞을까, 신형 기다릴까?"),
 ("el_t3b", "갤럭시 S25 어디서 사는 게 제일 싸?",              "갤럭시 S25 최저가로 사려면 어디서 사야 해?"),
 ("au_t0",  "현대차그룹에는 어떤 자동차 브랜드들이 있어?",      "현대차그룹 산하 자동차 브랜드가 뭐뭐야?"),
 ("au_t1a", "전기차 추천해줘",                                 "요즘 살만한 전기차 뭐가 있어?"),
 ("au_t1b", "패밀리 SUV 뭐가 좋아?",                           "가족용 SUV 추천해줘"),
 ("au_t2a", "아이오닉5 실제 타는 사람들 평이 어때?",           "아이오닉5 오너들 실제 후기 어때?"),
 ("au_t2b", "쏘렌토 하이브리드 살만해?",                       "쏘렌토 하이브리드 괜찮은 차야?"),
 ("au_t3a", "아이오닉5 살까 말까 고민인데 어떻게 생각해?",     "아이오닉5 사려고 고민 중인데 사는 게 맞을까?"),
 ("au_t3b", "쏘렌토 신형 나온다던데 기다리는 게 나아?",        "쏘렌토 풀체인지 기다릴까, 지금 모델 살까?"),
 ("fi_t0",  "카카오뱅크는 일반 은행이랑 뭐가 달라?",           "카카오뱅크가 기존 은행과 다른 점이 뭐야?"),
 ("fi_t1a", "신용카드 추천해줘",                               "요즘 쓸만한 신용카드 뭐가 있어?"),
 ("fi_t1b", "파킹통장 금리 높은 데 어디야?",                   "금리 높은 파킹통장 어디 게 좋아?"),
 ("fi_t2a", "KB국민카드 혜택 쓸만해?",                         "KB국민카드 혜택 괜찮은 편이야?"),
 ("fi_t2b", "카카오뱅크 세이프박스 이자 괜찮아?",              "카카오뱅크 세이프박스 금리 쓸만해?"),
 ("re_t0",  "쿠팡 와우 멤버십 혜택이 정확히 뭐야?",            "쿠팡 와우 멤버십 가입하면 뭐가 좋아?"),
 ("re_t1a", "온라인 장보기 어디가 제일 싸?",                   "온라인으로 장 볼 때 제일 저렴한 데가 어디야?"),
 ("re_t1b", "새벽배송 어디가 좋아?",                           "새벽배송 서비스 어디가 제일 나아?"),
 ("re_t2a", "로켓프레시랑 쓱배송 중에 뭐가 나아?",             "로켓프레시와 쓱배송 비교하면 어디가 좋아?"),
 ("re_t2b", "이마트 트레이더스 갈만해?",                       "이마트 트레이더스 쇼핑할 만해?"),
 ("fo_t0",  "CJ제일제당이랑 CJ는 무슨 관계야?",                "CJ제일제당은 CJ그룹이랑 어떤 관계야?"),
 ("fo_t1a", "만두는 어느 브랜드가 맛있어?",                    "냉동만두 맛있는 브랜드 어디야?"),
 ("fo_t1b", "간편식 추천해줘",                                 "요즘 괜찮은 간편식 뭐 있어?"),
 ("fo_t2a", "비비고 만두 맛있어?",                             "비비고 만두 맛 괜찮아?"),
 ("fo_t2b", "햇반 컵반 먹을만해?",                             "햇반 컵반 맛있어?"),
 ("te_t0",  "SKT 5G 요금제는 종류가 뭐뭐 있어?",               "SKT 5G 요금제 어떤 것들이 있어?"),
 ("te_t1a", "5G 요금제 어디 통신사가 제일 나아?",              "통신 3사 중 5G 요금제 어디가 좋아?"),
 ("te_t1b", "인터넷 결합상품 추천해줘",                        "인터넷 결합상품 어디 게 괜찮아?"),
 ("te_t2a", "SKT랑 KT 요금제 중에 뭐가 나아?",                 "SKT와 KT 중 요금제는 어느 쪽이 유리해?"),
 ("te_t2b", "KT 인터넷 결합하면 실제로 많이 싸져?",            "KT 인터넷 결합 할인 실제로 체감돼?"),
 ("te_t3a", "SKT에서 알뜰폰으로 갈아타면 손해야?",             "SKT 쓰다가 알뜰폰 넘어가도 괜찮아?"),
 ("te_t3b", "KT 인터넷 지금 바꾸면 위약금 때문에 손해야?",     "KT 인터넷 약정 중에 갈아타면 위약금이 더 커?"),
 ("es_t0",  "래미안은 어느 건설사 브랜드야?",                  "래미안 아파트는 어느 회사가 짓는 거야?"),
 ("es_t1a", "브랜드 아파트 순위가 어떻게 돼?",                 "아파트 브랜드 순위 알려줘"),
 ("es_t1b", "1군 아파트 브랜드가 어디어디야?",                 "1군 건설사 아파트 브랜드 뭐뭐 있어?"),
 ("es_t2a", "래미안 원베일리 살만해?",                         "래미안 원베일리 괜찮은 단지야?"),
 ("es_t2b", "힐스테이트 하자 많다던데 진짜야?",                "힐스테이트 하자 논란 실제로 심해?"),
]

ORIG = {q["id"]: q for q in collect.QUERIES_V2}

def build():
    """원문 메타(tier/industry/formulation/geo_tags) 승계 + text만 변형."""
    out = []
    for oid, _, para in PARA:
        o = ORIG[oid]
        out.append({"id": f"{oid}_p", "tier": o["tier"], "industry": o["industry"],
                    "formulation": o["formulation"], "text": para, "geo_tags": o["geo_tags"]})
    return out

def verify():
    print(f"[검수] 패러프레이즈 {len(PARA)}개 / 원문 QUERIES_V2 {len(ORIG)}개")
    errs = []
    ids = [p[0] for p in PARA]
    if len(set(ids)) != len(ids): errs.append("중복 원문 id 있음")
    missing = [i for i in ORIG if i not in ids]
    if missing: errs.append(f"패러프레이즈 누락 원문: {missing}")
    print("\n  [원문 대조] 지시서 표의 '원문' vs collect.py 실제 text")
    mism = 0
    for oid, said, para in PARA:
        if oid not in ORIG:
            print(f"  ✗ {oid}: 원문 id 없음"); errs.append(f"{oid} 없음"); continue
        real = ORIG[oid]["text"]
        if said != real:
            mism += 1
            print(f"  ✗ {oid}\n      지시서: {said}\n      실제  : {real}")
    if mism == 0: print("  ✓ 41/41 원문 완전 일치")
    print("\n  [변형 검수] 동일 문구·공백 이상")
    for oid, said, para in PARA:
        if para.strip() == ORIG.get(oid, {}).get("text", "").strip():
            print(f"  ✗ {oid}: 변형이 원문과 동일"); errs.append(f"{oid} 동일")
        if para != para.strip(): print(f"  ⚠ {oid}: 앞뒤 공백")
    Q = build()
    print(f"\n  [생성] para 질의 {len(Q)}개, id 예: {[q['id'] for q in Q[:3]]}")
    from collections import Counter
    print(f"  tier 분포: {dict(Counter(q['tier'] for q in Q))} (원문: {dict(Counter(o['tier'] for o in ORIG.values()))})")
    print(f"  industry 분포: {dict(Counter(q['industry'] for q in Q))}")
    for q in Q:
        offs = collect.OFFICIAL_DOMAINS.get(q["industry"], [])
        if not offs: errs.append(f"{q['id']} 공식도메인 없음")
    print(f"  공식도메인 등록: 전 질의 산업키 매칭 {'OK' if not errs else errs}")
    print(f"\n  예상 수집: {len(Q)}질의 × 4엔진 × 3회 = {len(Q)*4*3}런")
    print("\n[결과]", "✓ 검수 통과 — 수집 승인 대기" if not errs else f"✗ 문제 {len(errs)}건: {errs}")
    return errs

if __name__ == "__main__":
    verify()
