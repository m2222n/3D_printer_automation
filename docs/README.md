# Documents

> 프로젝트 설계 문서 및 가이드
> 🚨 **현행 판단·현황의 정본은 `CLAUDE.md`(+ `CLAUDE.local.md`)다.** 여기 문서는 설계·레퍼런스.

## 현행 문서

| 문서 | 설명 | 날짜 |
|------|------|------|
| `MES_ERP_ATS_기능정의_0710.md` | ⭐ Lite MES/ERP/ATS 3계층 기능정의 (SaaS 고도화 지시 답) | 2026-07-10 |
| `binpicking_summary.md` | 빈피킹 전체 현황 정리 (ORINU-DEV-2026-002) | 갱신 중 |
| `한솔코에버_API_가이드라인.md` | 협업용 API 가이드라인 | 2026-02-24 |
| `Phase2_LocalAPI_아키텍처설계.md` | Phase 2 Local API 아키텍처 | 2026-02-02 |
| `Phase4_OpenMV_개발설계서.md` | Phase 4 장비 모니터링 설계 | 2026-03-09 |
| `WireGuard_LAN_VPN_연결_가이드.md` | WireGuard VPN 연결 가이드 | 2026-02-05 |
| `Phase1_WebAPI_개발설계서.docx` | Phase 1 초기 설계서 | 2026-01 |

⚠️ `Phase4_OpenMV_개발설계서.md`는 **OpenMV AE3 시기** 문서다. 7/16 대표님 회의로
**OpenMV N6로 전환 + 경화기는 자동화 대상에서 제외**됐다 → `memory/project_ceo_meeting_0716.md`.

## 하위 폴더

| 폴더 | 내용 |
|---|---|
| `hansol_handover/` | 협력사 인계 자료(바텀비전 인터페이스 등) |
| `meeting_records/` | (비어 있음) |
| ⛔ `archive_track1_202605/` | 빈피킹 트랙1(6DoF/FPFH)·트랙2(YOLO) 시기 문서 — **depth_track 전환으로 사문화** |
| ⛔ `archive_meetings_202604_05/` | 4~5월 회의 자료 — 결정 요약은 그 폴더 README |
| ⛔ `archive_purchase_202607/` | 7월 지원사업 구매 조사 — **7/24 미팅으로 전제 다수 무효** |
| ⛔ `archive_202604/` | 4~5월 일회성 문서(체크리스트·보고 입력자료 등) |

> ⛔ 표시 폴더는 **이력 보존용**이다. 지우지 않은 이유는 `CLAUDE.md`가 당시 판단 근거로
> 인용하기 때문이고, 각 폴더 README에 **"무엇이 대체했나 / 무엇이 뒤집혔나"**를 적어 두었다.
