#!/usr/bin/env python3
"""
2차 웨이브 수집 — 패러프레이즈 41(para_v1, 492런) + 푸조 프로브(probe_import_v1, 24런) = 516런
- 기존 collect.py 파이프라인 재사용(run_collection). main_v2·pilot_sme_v1 불변.
- 오세 승인(2026-07-16): 전체 516런 ~$38. 엔진별 캡 ChatGPT $22 / Claude $22(지시서 $18→정정) /
  Perplexity $2 / Gemini $2, 합산 강제중단 $40.
- 실측 단가(파일럿): chatgpt $0.1453, claude $0.1490 → 129런/엔진 투영 $38.19.
- 프로브를 먼저 수집(24런 ~$1.8 선확보) 후 para 492런.
"""
import sys, os, time, requests
import collect_paper1 as collect
from collect_paper1 import (run_collection, OFFICIAL_DOMAINS, _gt,
                     get_completed_set, AUTO_ENGINE_KEYS)
from para_queries import build as build_para, verify as verify_para

BATCH_PARA="para_v1"; BATCH_PROBE="probe_import_v1"
for b in (BATCH_PARA, BATCH_PROBE):
    assert b != collect.MAIN_BATCH and b != "pilot_sme_v1", "★ 기존 배치 오염 금지"

U=os.getenv("SUPABASE_URL"); K=os.getenv("SUPABASE_SECRET_KEY")

# ── 푸조 프로브: 전용 산업키 (대기업 도메인 오염 차단) ──
OFFICIAL_DOMAINS["자동차_probe"]=[("epeugeot.co.kr","owned_corp"),("peugeot.com","owned_corp")]
PROBE=[
 {"id":"probe_pg_t0","tier":"T0","industry":"자동차_probe","formulation":"사실-사업구조",
  "text":"푸조는 어떤 회사야?",   "geo_tags":_gt("factual","research","fact")},
 {"id":"probe_pg_t2","tier":"T2","industry":"자동차_probe","formulation":"구매가치형",
  "text":"푸조 3008 살만해?",     "geo_tags":_gt("opinion","consideration","opinion")},   # au_t2b 문형 치환
]
PARA=build_para()

# ── 비용 캡 (오세 승인) ──
collect.COST_CAPS.update({"chatgpt":22.0,"claude":22.0,"perplexity":2.0,"gemini":2.0})
TOTAL_CAP=40.0
N_RUNS=3

def spent_total(): return sum(t["spent"] for t in collect._tracker.values())

def seed_both():
    """★ collect.seed_tracker_from_db는 값을 덮어씀 → 두 배치 합산 시딩을 직접 구현."""
    agg={}
    for b in (BATCH_PARA, BATCH_PROBE):
        try:
            r=requests.get(f"{U}/rest/v1/citation_collection?batch_label=eq.{b}"
                           f"&error=is.null&select=engine,cost_est",
                           headers={"apikey":K,"Authorization":f"Bearer {K}"},timeout=30)
            r.raise_for_status()
            for x in r.json():
                e=x.get("engine"); agg[e]=agg.get(e,0.0)+(x.get("cost_est") or 0)
        except Exception as ex:
            print(f"[시딩 실패—0에서 시작] {b}: {str(ex)[:60]}")
    for e,s in agg.items():
        if e in collect._tracker:
            collect._tracker[e]["spent"]=s
            cap=collect.COST_CAPS.get(e)
            if cap is not None and s>=cap: collect._tracker[e]["stopped"]=True
    if agg: print("[누적캡 시딩(2배치 합산)] "+", ".join(f"{e}=${v:.2f}" for e,v in agg.items()))

def guard(tag):
    s=spent_total()
    print(f"  [비용] {tag} 누적 ${s:.2f} / 강제중단 ${TOTAL_CAP}")
    capped=[e for e,t in collect._tracker.items() if t["stopped"]]
    if capped: print(f"  ★ 캡 도달 엔진: {', '.join(capped)} — 해당 엔진만 중단, 나머지 계속")
    if s>TOTAL_CAP:
        print(f"★ 합산 강제중단 ${TOTAL_CAP} 초과 (${s:.2f}) — 수집 중단, 보고 필요")
        sys.exit(2)

def main():
    errs=verify_para()
    assert not errs, f"패러프레이즈 검수 실패: {errs}"
    print(f"\n[2차 웨이브] 수집일 {time.strftime('%Y-%m-%d')} | "
          f"probe {len(PROBE)}질의×4×{N_RUNS}={len(PROBE)*4*N_RUNS}런 + "
          f"para {len(PARA)}질의×4×{N_RUNS}={len(PARA)*4*N_RUNS}런 = {(len(PROBE)+len(PARA))*4*N_RUNS}런")
    print(f"[가드] 엔진별 캡 chatgpt$22/claude$22/perp$2/gem$2, 합산 강제중단 ${TOTAL_CAP} | main_v2 조회 0건")
    seed_both()

    # ── 1) 프로브 먼저 (24런, ~$1.8 선확보) ──
    print(f"\n{'='*60}\n[프로브] batch={BATCH_PROBE}\n{'='*60}")
    cp=get_completed_set(BATCH_PROBE); print(f"[재개] 기완료 {len(cp)}건")
    for run in range(1,N_RUNS+1):
        run_collection(PROBE, AUTO_ENGINE_KEYS, BATCH_PROBE, run, cp)
        guard(f"probe run={run}")

    # ── 2) 패러프레이즈 492런 ──
    print(f"\n{'='*60}\n[패러프레이즈] batch={BATCH_PARA}\n{'='*60}")
    ca=get_completed_set(BATCH_PARA); print(f"[재개] 기완료 {len(ca)}건")
    for run in range(1,N_RUNS+1):
        run_collection(PARA, AUTO_ENGINE_KEYS, BATCH_PARA, run, ca)
        guard(f"para run={run}")

    # ── 3) 재조회 assert ──
    print(f"\n{'='*60}\n[검증] 수집 후 재조회\n{'='*60}")
    for b,exp in ((BATCH_PARA,492),(BATCH_PROBE,24)):
        r=requests.get(f"{U}/rest/v1/citation_collection?batch_label=eq.{b}&error=is.null&select=id",
                       headers={"apikey":K,"Authorization":f"Bearer {K}","Prefer":"count=exact",
                                "Range":"0-0"},timeout=30)
        cnt=r.headers.get("content-range","?/?").split("/")[-1]
        print(f"  {b}: 성공 {cnt} / 목표 {exp} {'✓' if str(cnt)==str(exp) else '★ 결측 — null 정직표기'}")
    capped=[e for e,t in collect._tracker.items() if t["stopped"]]
    if capped: print(f"[비용 가드] 캡 도달: {', '.join(capped)}")
    print(f"\n[완료] 누적 ${spent_total():.2f}")

if __name__=="__main__":
    main()
