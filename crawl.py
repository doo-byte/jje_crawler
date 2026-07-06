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
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
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
# 주의: 제남도서관=남원읍(서귀포시), 동녘도서관=구좌읍 세화(제주시)
SEOGWIPO_HINTS = ["서귀포", "본원(서귀포시)", "[송악]", "[삼매봉]", "[제남]",
                  "송악도서관", "삼매봉도서관", "제남도서관", "대정", "표선", "남원읍"]
JEJUSI_HINTS = ["제주시", "신제주", "동부외국", "서부외국", "제주학생문화원",
                "회천분원", "제주교육박물관", "제주다문화", "제주외국어학습센터",
                "제주융합과학연구원", "[동녘]", "[우당]", "[탐라]", "[한수풀]",
                "[김녕]", "동녘도서관", "우당도서관", "탐라도서관", "한수풀도서관",
                "김녕도서관"]

# 기관/시설 키워드 → 좌표 (위도, 경도)
# 출처: 제주평생교육다모아(damoa.jeju.kr) 시설 지도 + OpenStreetMap
ORG_COORDS = {
    "동부외국문화학습관": (33.44297, 126.91113),   # 구좌읍 세화
    "서부외국문화학습관": (33.41141, 126.26071),   # 한림
    "신제주외국문화학습관": (33.47242, 126.48199),  # 제주시 연동
    "서귀포외국문화학습관": (33.25854, 126.56193),  # 서귀포 동홍동
    "제주외국어학습센터": (33.50405, 126.52211),
    "제주국제교육원": (33.50405, 126.52211),
    "제주융합과학연구원": (33.50441, 126.51964),   # 제주시 전농로 88 (수학체험관)
    "제주수학체험관": (33.50441, 126.51964),
    "제주학생문화원": (33.50128, 126.54044),
    "서귀포학생문화원": (33.25864, 126.56169),
    "서귀포도서관": (33.25860, 126.56214),        # 서귀포학생문화원 부지
    "송악도서관": (33.22662, 126.24914),          # 대정읍
    "제남도서관": (33.27963, 126.70496),          # 남원읍
    "동녘도서관": (33.52173, 126.85330),          # 구좌읍 세화
    "삼매봉도서관": (33.24488, 126.55124),
    "우당도서관": (33.51514, 126.54840),
    "탐라도서관": (33.47916, 126.47625),
    "한수풀도서관": (33.42018, 126.26851),        # 한림
    "애월도서관": (33.46330, 126.33129),
    "조천도서관": (33.53773, 126.66768),
    "함덕도서관": (33.54177, 126.66479),
    "표선도서관": (33.32390, 126.83850),
    "성산일출도서관": (33.45572, 126.91211),
    "한경도서관": (33.35006, 126.18452),
    "제주도서관": (33.49993, 126.54107),
    "한라도서관": (33.47618, 126.51616),
    "제주교육박물관": (33.49444, 126.53834),
    "제주다문화교육센터": (33.54835, 126.65390),
    "제주유아교육진흥원": (33.25854, 126.56193),   # 본원(서귀포)
    "서귀포시교육지원청": (33.27057, 126.58922),   # 토평동
    "제주시교육지원청": (33.49393, 126.53831),
    "학생안전지원과(서귀포)": (33.27057, 126.58922),
    "학생안전지원과(제주시)": (33.49393, 126.53831),
    "서귀포시진로교육지원센터": (33.27057, 126.58922),  # 교육지원청 내
    "제주시진로교육지원센터": (33.49393, 126.53831),
}


def infer_coords(item):
    """기관명 → 장소 문자열 → 제목 순으로 좌표 추정."""
    for blob in (item.get("org", ""), item.get("place", ""), item.get("title", "")):
        for key, coord in ORG_COORDS.items():
            if key in blob:
                return coord
    return None


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
            val = m.group(1).strip()
            # 빈 항목이면 다음 필드 라벨이 잡히므로 제거
            if any(val.startswith(lab) for lab in
                   ("분류", "교육방법", "모집인원", "신청인원", "교육대상",
                    "교육장소", "신청방법", "문의", "세부사항")):
                val = ""
            out[key] = val
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
        coord = infer_coords(item)
        item["lat"], item["lng"] = coord if coord else (None, None)
        if i % 10 == 0:
            print(f"  {i}/{len(items)}")
        time.sleep(0.2)

    data = sorted(items.values(), key=lambda x: x["applyPeriod"])
    out = Path(__file__).parent / "data.js"
    payload = ("const CRAWLED_AT = " + json.dumps(datetime.now(KST).strftime("%Y-%m-%d %H:%M")) +
               ";\nconst EDU_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    out.write_text(payload, encoding="utf-8")
    print(f"완료: {out} ({len(data)}건). index.html 을 브라우저로 여세요.")


if __name__ == "__main__":
    main()
