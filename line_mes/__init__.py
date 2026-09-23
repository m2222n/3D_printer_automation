"""
line_mes — 라인 MES 관측 도메인 (M1 토폴로지 · M3a 상태 엔진 · M4 스키마).

web-api(HTTP 계층 app/line)와 sequence_service(M2b Moved 발행)가 둘 다 import 하므로
어느 서비스 폴더에도 넣지 않고 리포 루트 패키지로 둔다. 설치 = 루트 requirements.txt 의 `-e .`.
제어(sequence_service)는 이 패키지를 호출만 하고, 이 패키지는 제어를 모른다 (병존 원칙).
"""
