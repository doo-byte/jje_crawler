# 우리 가족 제주 교육/강좌 알리미

[제주특별자치도교육청 통합예약시스템](https://org.jje.go.kr/reserve/jjeEducation/list.jje?menuCd=DOM_000000502001000000)의
교육/강좌 중 **접수중·접수예정** 건을 모아 보여주는 대시보드입니다.

- 접수 마감 D-day 표시 (3일 이내 임박 강조)
- 가족 구성원별 필터: 첫째(초6) / 둘째(6세) / 부모·가족 — 세부사항의 학년·나이 표기를 자동 분석
- 서귀포시 강좌 우선 정렬

## 구조

| 파일 | 역할 |
|---|---|
| `crawl.py` | 목록·상세 페이지 크롤링 → `data.js` 생성 (표준 라이브러리만 사용) |
| `index.html` | `data.js`를 읽어 렌더링하는 정적 대시보드 |
| `.github/workflows/crawl-and-deploy.yml` | 매일 KST 06/12/18시 크롤링 후 GitHub Pages 배포 |

## 로컬 실행

```bash
python crawl.py   # data.js 생성 (~30초)
# index.html을 브라우저로 열기
```

※ 학년·나이 판별은 자동 분석이므로 신청 전 반드시 원문 상세 페이지를 확인하세요.
