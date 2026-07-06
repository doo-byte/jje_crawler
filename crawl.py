# -*- coding: utf-8 -*-
"""제주특별자치도교육청 통합예약시스템(org.jje.go.kr) 교육/강좌 크롤러.

접수중(reserveStatus=1)·예정(reserveStatus=0) 강좌를 모두 수집하고,
상세 페이지에서 모집인원/교육대상/세부사항을 가져와 data.js 로 저장한다.
index.html 을 브라우저로 열면 data.js 를 읽어 대시보드를 보여준다.

사용법:  python crawl.py
"""
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from html import unescape
from pathlib import Path

BASE = "https://org.jje.go.kr"
LIST_URL = (BASE + "/reserve/jjeEducation/list.jje"
            "?menuCd=DOM_000000502001000000&reserveStatus={status}&startPage={page}")
VIEW_URL = (BASE + "/reserve/jjeEducation/view.jje"
            "?menuCd=DOM_000000502002000000&educationSid={sid}")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 운영기관명/제목 → 지역 매핑 (기관명에 지역이 안 드러나는 곳만 명시)
# 도서관은 제목 앞머리 [송악] 같은 표기로 구분
SEOGWIPO_HINTS = ["서귀포", "본원(서귀포시)", "[송악]", "[삼매봉]", "[동녘]",
                  "송악도서관", "삼매봉도서관", "동녘도서관", "대정", "표선", "남원읍"]
JEJUSI_HINTS = ["제주시", "신제주", "동부외국", "서부외국", "제주학생문화원",
                "회천분원", "제주교육박물관", "제주다문화", "제주외국어학습센터",
                "제주융합과학연구원", "[제남]", "[우당]", "[탐라]", "[한수풀]",
                "[김녕]", "제남도서관", "우당도서관", "탐라도서관", "한수풀도서관",
                "김녕도서관"]


def fetch(url, retry=3):
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        except Exception as e:
            if i == retry - 1:
                raise
            print(f"  재시도 {i+1}: {e}", file=sys.stderr)
            time.sleep(2)


def strip_tags(html):
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    html = re.sub(r"<br\s*/?>", "\n", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = unescape(html).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", html)


def parse_list_page(src):
    """목록 페이지에서 행 단위 정보 추출."""
    rows = []
    for tr in re.findall(r"<tr>\s*<td data-cell-header.*?</tr>", src, flags=re.S):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, flags=re.S)
        if len(tds) < 7:
            continue
        sid_m = re.search(r"educationSid=(ED_\d+)", tr)
        if not sid_m:
            continue
        org = strip_tags(tds[1]).strip()
        title = strip_tags(tds[2]).strip()
        edu_period = strip_tags(tds[3]).strip()
        apply_period = strip_tags(tds[4]).strip()
        targets = [t for t in strip_tags(tds[5]).split() if t]
        status = strip_tags(tds[6]).strip()
        rows.append({
            "sid": sid_m.group(1),
            "org": re.sub(r"\s+", " ", org),
            "title": title,
            "eduPeriod": edu_period,
            "applyPeriod": apply_period,
            "targets": targets,
            "status": status,
        })
    max_page = max([int(p) for p in re.findall(r"linkPage\((\d+)\)", src)] or [1])
    return rows, max_page


def parse_detail(src):
    """상세 페이지에서 추가 필드 추출."""
    text = strip_tags(src)
    out = {}
    for key, field in [("category", "분류"), ("method", "교육방법"),
                       ("capacity", "모집인원"), ("applied", "신청인원"),
                       ("place", "교육장소"), ("contact", "문의")]:
        m = re.search(re.escape(field) + r"\s*\n?\s*([^\n]*)", text)
        if m:
            out[key] = m.group(1).strip()
    # 세부사항 본문 (대상 학년/나이 판단용)
    m = re.search(r"세부사항\s*(.*?)\s*목록보기", text, flags=re.S)
    out["detail"] = re.sub(r"\s+", " ", m.group(1)).strip()[:1500] if m else ""
    return out


def infer_region(org, title):
    blob = org + " " + title
    if any(h in blob for h in SEOGWIPO_HINTS):
        return "서귀포시"
    if any(h in blob for h in JEJUSI_HINTS):
        return "제주시"
    return "기타/공통"


NUM = r"(\d)"


def infer_fit(item):
    """가족 구성원별 적합 여부: 첫째(초6), 둘째(6세), 부모."""
    targets = set(item["targets"])
    detail = item.get("detail", "") + " " + item["title"]
    fit = {"child12": False, "child6": False, "parent": False}

    # 부모: 학부모/일반/가족 대상이면 해당
    if targets & {"학부모", "일반", "가족"}:
        fit["parent"] = True

    # 둘째(6세, 유아)
    if "유아" in targets or "가족" in targets:
        ages = re.findall(r"(\d{1,2})\s*[~∼-]\s*(\d{1,2})\s*세", detail)
        singles = re.findall(r"(\d{1,2})\s*세", detail)
        if ages:
            fit["child6"] = any(int(a) <= 6 <= int(b) for a, b in ages)
        elif singles:
            fit["child6"] = any(int(s) == 6 for s in singles)
        else:
            fit["child6"] = True  # 나이 명시 없으면 유아 대상으로 간주

    # 첫째(초6, 학생)
    if "학생" in targets or "가족" in targets:
        ok = None
        # "4~6학년", "초등 3-4학년" 등 범위
        for a, b in re.findall(r"(\d)\s*[~∼·,-]\s*(\d)\s*학년", detail):
            near = detail  # 초등 문맥 확인
            is_elem = ("초등" in near) or ("중학" not in near and "고등" not in near)
            hit = int(a) <= 6 <= int(b) and is_elem
            ok = hit if ok is None else (ok or hit)
        # 단일 "6학년"
        if ok is None:
            singles = re.findall(r"(\d)\s*학년", detail)
            if singles:
                ok = "6" in singles and "중학" not in detail and "고등" not in detail
        # "초등학생", "초등" 만 있는 경우
        if ok is None:
            if "초등" in detail:
                ok = True
            elif "중학" in detail or "고등" in detail:
                ok = False
        fit["child12"] = True if ok is None else ok  # 판단 불가 시 포함(놓치지 않게)

    return fit


def main():
    items = {}
    for status in ("1", "0"):  # 접수중 먼저, 그다음 예정
        page = 1
        while True:
            print(f"목록 수집: 상태={status} 페이지={page}")
            src = fetch(LIST_URL.format(status=status, page=page))
            rows, max_page = parse_list_page(src)
            for r in rows:
                items[r["sid"]] = r
            if page >= max_page:
                break
            page += 1
            time.sleep(0.3)

    print(f"총 {len(items)}건 → 상세 수집 중...")
    for i, (sid, item) in enumerate(items.items(), 1):
        try:
            item.update(parse_detail(fetch(VIEW_URL.format(sid=sid))))
        except Exception as e:
            print(f"  상세 실패 {sid}: {e}", file=sys.stderr)
        item["url"] = VIEW_URL.format(sid=sid)
        item["region"] = infer_region(item["org"], item["title"])
        item["fit"] = infer_fit(item)
        if i % 10 == 0:
            print(f"  {i}/{len(items)}")
        time.sleep(0.2)

    data = sorted(items.values(), key=lambda x: x["applyPeriod"])
    out = Path(__file__).parent / "data.js"
    payload = ("const CRAWLED_AT = " + json.dumps(datetime.now().strftime("%Y-%m-%d %H:%M")) +
               ";\nconst EDU_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    out.write_text(payload, encoding="utf-8")
    print(f"완료: {out} ({len(data)}건). index.html 을 브라우저로 여세요.")


if __name__ == "__main__":
    main()
