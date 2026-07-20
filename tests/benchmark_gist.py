"""
GiST 공간 인덱스 실측 벤치마크 — 100만 건 규모
=================================================
전수비교(ST_Distance, O(N)) vs GiST 인덱스(ST_DWithin, O(log N)) 반경 탐색 성능을
합성 데이터 100만 건으로 실측한다.

사용법:
  1) Docker로 로컬 PostGIS 실행 (Supabase를 쓰지 않는 이유: 무료 티어 용량/부하 보호)
     docker run -d --name bench-postgis -e POSTGRES_PASSWORD=bench -p 5433:5432 postgis/postgis:16-3.4
  2) pip install psycopg2-binary
  3) python benchmark_gist.py
     (다른 DB를 쓰려면: python benchmark_gist.py --dsn "postgresql://user:pw@host:port/db")

출력: 각 방식의 실행 시간(5개 지점 x 3회, 중앙값)과 이력서용 요약 문구.
결과 파일: benchmark_result.md
"""
import argparse
import random
import statistics
import time

import psycopg2

N_ROWS = 1_000_000
RADIUS_M = 3_000          # 반경 3km 탐색
N_CENTERS = 5             # 서로 다른 기준 좌표 5개
N_REPEAT = 3              # 좌표당 반복 횟수
# 대한민국 대략 경계 (경도 126~129.5, 위도 33~38.6)
LON_MIN, LON_SPAN = 126.0, 3.5
LAT_MIN, LAT_SPAN = 33.0, 5.6


def bench_query(cur, sql, params, repeat):
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        cur.execute(sql, params)
        cur.fetchall()
        times.append(time.perf_counter() - t0)
    return times


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default="postgresql://postgres:bench@localhost:5433/postgres")
    ap.add_argument("--rows", type=int, default=N_ROWS)
    args = ap.parse_args()

    conn = psycopg2.connect(args.dsn)
    conn.autocommit = True
    cur = conn.cursor()

    print(f"[1/5] 테이블 생성 및 합성 데이터 {args.rows:,}건 적재 (서버측 생성, 수십 초 소요)")
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    cur.execute("DROP TABLE IF EXISTS bench_places;")
    cur.execute("""
        CREATE TABLE bench_places (
            id   serial PRIMARY KEY,
            name text,
            geog geography(Point, 4326)
        );
    """)
    cur.execute(f"""
        INSERT INTO bench_places (name, geog)
        SELECT 'place_' || g,
               ST_SetSRID(ST_MakePoint({LON_MIN} + random() * {LON_SPAN},
                                       {LAT_MIN} + random() * {LAT_SPAN}), 4326)::geography
        FROM generate_series(1, {args.rows}) AS g;
    """)
    cur.execute("ANALYZE bench_places;")

    random.seed(42)
    centers = [(LON_MIN + random.random() * LON_SPAN,
                LAT_MIN + random.random() * LAT_SPAN) for _ in range(N_CENTERS)]

    # ---- A. 전수비교 (인덱스 없음, ST_Distance) ----
    print("[2/5] A. 전수비교 ST_Distance — 인덱스 없이 측정")
    sql_a = """
        SELECT count(*) FROM bench_places
        WHERE ST_Distance(geog, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) < %s;
    """
    times_a = []
    for lon, lat in centers:
        times_a += bench_query(cur, sql_a, (lon, lat, RADIUS_M), N_REPEAT)

    # ---- B. GiST 인덱스 + ST_DWithin ----
    print("[3/5] GiST 인덱스 생성 (수 분 소요될 수 있음)")
    cur.execute("CREATE INDEX idx_bench_geog ON bench_places USING GIST (geog);")
    cur.execute("ANALYZE bench_places;")

    print("[4/5] B. GiST + ST_DWithin 측정")
    sql_b = """
        SELECT count(*) FROM bench_places
        WHERE ST_DWithin(geog, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s);
    """
    times_b = []
    for lon, lat in centers:
        times_b += bench_query(cur, sql_b, (lon, lat, RADIUS_M), N_REPEAT)

    # ---- 결과 ----
    med_a, med_b = statistics.median(times_a), statistics.median(times_b)
    speedup = med_a / med_b if med_b > 0 else float("inf")

    cur.execute("SELECT version();")
    pg_ver = cur.fetchone()[0].split(",")[0]

    report = f"""# GiST 공간 인덱스 실측 벤치마크 결과

- 환경: {pg_ver} / 합성 데이터 {args.rows:,}건 / 반경 {RADIUS_M:,}m / 기준 좌표 {N_CENTERS}개 x {N_REPEAT}회
- 측정 방식: 클라이언트 측 wall-clock, 중앙값 기준

| 방식 | 중앙값 | 최소 | 최대 |
|---|---|---|---|
| A. 전수비교 ST_Distance (인덱스 없음) | {med_a:.3f}s | {min(times_a):.3f}s | {max(times_a):.3f}s |
| B. GiST 인덱스 + ST_DWithin | {med_b:.3f}s | {min(times_b):.3f}s | {max(times_b):.3f}s |

**개선 배율: 약 {speedup:,.0f}배 ({med_a:.2f}초 → {med_b:.3f}초)**

이력서용 문구(실측):
"합성 데이터 100만 건 실측 기준, 반경 탐색 {med_a:.1f}초 → {med_b:.3f}초(약 {speedup:,.0f}배) 개선"
"""
    with open("benchmark_result.md", "w", encoding="utf-8") as f:
        f.write(report)

    print("[5/5] 완료 — 결과는 benchmark_result.md 저장")
    print(report)

    cur.execute("DROP TABLE bench_places;")  # 정리 (남기려면 이 줄 삭제)
    conn.close()


if __name__ == "__main__":
    main()
