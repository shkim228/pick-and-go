# 🧳 Pick & Go — PostGIS 공간 인덱스와 Saga 패턴 기반 맞춤형 여행 서비스

출발지·목적지·여행 기간·스타일 등의 조건을 입력하면 맞춤 일정을 자동 생성하고, 항공·숙소를 일괄 예약하는 엔드-투-엔드 여행 서비스입니다.

이 저장소는 시스템 전체 중 **DB부**(공간 데이터베이스 설계)와 **예약부**(분산 예약 파이프라인) 두 서브시스템을 담당한 캡스톤 설계 프로젝트입니다.

> 🔗 배포: https://pick-and-go-tau.vercel.app

> 📄 프로젝트 전체 설계 및 검증 과정은 [`docs/thesis_chapter1_intro.md`](docs/thesis_chapter1_intro.md) ~ [`thesis_chapter9_conclusion.md`](docs/thesis_chapter9_conclusion.md)에서 장별로 확인하실 수 있습니다.

---

## 📌 핵심 성과

| 구분 | 내용 |
|---|---|
| 조회 성능 | 반경 탐색을 전수비교(`ST_Distance`, O(N))에서 **GiST 공간 인덱스 기반 `ST_DWithin`(O(log N))**으로 전환 — 합성 데이터 **100만 건 실측 0.529초 → 0.002초(약 314배)**. 실서비스 데이터 1,533건 기준으로는 0.083초 → 0.063초 |
| 예약 정합성 | **Saga 패턴 보상 트랜잭션**으로 항공·숙소 예약 부분 실패 시 자동 롤백 — 부분 결제·고아 트랜잭션 방지 |
| 외부 API 연동 | 항공(**Duffel**)·숙소(**LiteAPI**)·이메일(**Resend**) 실 API를 테스트/샌드박스 모드로 연동, 환경변수로 Mock ↔ 실 API 전환 |
| 처리 최적화 | 이동 시간 계산을 외부 지도 API 반복 호출 대신 **Haversine 공식**으로 대체, 대량 수집은 **배치 Bulk Upsert**로 DB I/O 절감 |
| 검증 | 예약 파이프라인 **E2E 6개 시나리오(TC-E2E-01~06)** — 정상 흐름·부분 실패 롤백·확정 실패·저장 실패·타임아웃·이메일 발송 3-way 검증 |

> 성능 수치: 100만 건 구간은 직접 작성한 벤치마크 스크립트([`tests/benchmark_gist.py`](tests/benchmark_gist.py))로 **실측**했습니다.

> 측정 조건 — Docker / PostgreSQL 16.4 + PostGIS, 합성 데이터 1,000,000행, 반경 3km, 서로 다른 좌표 5개 × 3회 반복의 중앙값.

> 초기 문서의 복잡도 기반 추정값을 실측값으로 대체했습니다. 상세는 [`docs/thesis_chapter4_gist_optimization.md`](docs/thesis_chapter4_gist_optimization.md) 참조.

---

## 🏗 담당 영역

### DB부 — 공간 데이터베이스 설계
- 로컬 파일 DB(SQLite)에서 **Supabase 클라우드 PostgreSQL**로 마이그레이션 — 다중 접속·확장성 확보 (SQLAlchemy 직접 연결)
- PostgreSQL의 공간 확장 모듈 **PostGIS**로 장소 좌표를 Geography 타입으로 저장
- 전수비교(`ST_Distance`) 방식을 **GiST 공간 인덱스 기반 `ST_DWithin`**으로 전환하여 반경 탐색 성능 개선
- 대량 수집 데이터의 반복 DB 접속 부하를 줄이기 위한 **배치 Bulk Upsert + TTL(180일) 캐시 정책** 설계

### 예약부 — 분산 예약 파이프라인
- 항공(**Duffel API v2**)·숙소(**LiteAPI Sandbox**)·이메일(**Resend**) 실 API를 테스트/샌드박스 모드로 연동, 비동기 병렬 호출로 처리 시간 단축 (환경변수 `MOCK_FLIGHT`·`MOCK_HOTEL`로 Mock ↔ 실 API 전환)
- 부분 실패(예: 항공 예약 성공 후 숙소 예약 실패) 상황에서 데이터 정합성이 깨지는 문제를 **Saga 패턴 보상 트랜잭션**으로 해결
- 파트너사 무응답 대비 **10초 타임아웃**, 검증 → 외부연동 → 확정 → 저장 → 알림의 **5단계 파이프라인(Sub1~Sub5)** 설계

---

## 🛠 기술 스택

**Backend**: Python, FastAPI, PostgreSQL(Supabase 클라우드), PostGIS, SQLAlchemy, Alembic

**Frontend**: Next.js, TypeScript

**외부 API**: Duffel(항공), LiteAPI(숙소), Resend(이메일)

**설계 기법**: GiST 공간 인덱스, Saga 패턴(보상 트랜잭션), 비동기 병렬 처리(asyncio)

---

## 📁 폴더 구조

```
app/                 FastAPI 백엔드 (main.py, 예약 파이프라인 reservation/Sub1~Sub5)
backend_postgres.py  PostgreSQL + PostGIS 데이터 접근 계층 (장소·이동시간 조회)
travel_logic/        일정 생성 로직 (도메인 · 서비스 · 전략 패턴)
config.py            환경 설정
db/                  DB 연결 및 스키마 정의
alembic/             DB 마이그레이션
frontend/            Next.js 프론트엔드
tests/               E2E 예약 파이프라인 테스트 · 쿼리 벤치마크
docs/                논문 챕터, 아키텍처 다이어그램, 성능 그래프
scripts/             데이터 수집 및 마이그레이션 스크립트
```

---

## 📚 상세 문서

- 논문 전체: [`docs/`](docs) 폴더의 `thesis_chapter1_intro.md` ~ `thesis_chapter9_conclusion.md`
- 성능 벤치마크 그래프: [`docs/figure9_performance_graph.png`](docs/figure9_performance_graph.png)
- Saga 패턴 흐름도: [`docs/figure5_saga_flowchart.png`](docs/figure5_saga_flowchart.png)
- 개발 기여 가이드: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- 100만 건 실측 벤치마크: [`tests/benchmark_gist.py`](tests/benchmark_gist.py) · [`docs/benchmark_result.md`](docs/benchmark_result.md)

---

## ⚠️ 한계와 남은 과제

[#-한계와-남은-과제](#-한계와-남은-과제)

- **쓰기 성능·동시 접속 미검증** — 인덱스는 조회를 빠르게 하는 대신 데이터 추가·수정 비용을 늘립니다. 이번 측정은 조회에 한정되어, 쓰기 성능 저하와 다중 접속 환경의 영향은 확인하지 못했습니다.
- **보상 트랜잭션 자체의 실패** — 롤백을 시도하는 요청도 실패할 수 있으나 현재는 로그로만 남습니다. 멱등성을 보장한 재시도와 수동 처리 대기열이 다음 보완 지점입니다.
- **운영 관측 체계 부재** — 배포는 자동화했지만 로그 수집과 장애 알림이 없어, 문제가 생겨도 사용자 신고 전에는 알기 어렵습니다.

---

## 👥 팀

Team Y — 이영민(처리부), 김재학(입력·출력부), **김수호(DB부·예약부 — 본 저장소 담당)**
