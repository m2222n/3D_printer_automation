"""
빈피킹 DB 모델
==============
SQLAlchemy ORM 모델 (binpick_scenes, binpick_detections)

⭐ 왜 두 테이블인가
------------------
장면(scene)은 **"한 번 촬영해서 추론한 결과"** 이고 검출(detection)은 그 안의
부품 하나다. 웹 화면이 묻는 것은 두 층위로 갈린다:
  - "지금 잘 돌고 있나" → 장면 단위(검출 수·게이트 판정·지연)
  - "무엇을 어디서 찾았나" → 검출 단위

🚨 게이트 판정을 장면 테이블의 **1급 컬럼**으로 둔다.
   8/6 게이트 설계의 요점이 *"판정 없이 검출 수만 보면 c3처럼 배경을 부품으로
   잡은 결과가 정상처럼 보인다"* 였다. JSON 안에 묻어두면 조회·필터가 안 되고,
   그러면 결국 아무도 안 본다.

⚠️ `not_checked`를 기본값으로 둔다 — **판정이 없는 것과 판정이 통과인 것은 다르다.**
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, Index
from sqlalchemy.sql import func
import uuid

from app.local.models import Base


class BinPickScene(Base):
    """빈피킹 인식 장면 1건 (= 촬영 1회 + 추론 1회)"""
    __tablename__ = "binpick_scenes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # 모듈이 보낸 장면 식별자. 🚨 유일성을 신뢰하지 않는다(외부 유래).
    scene_id = Column(String(120), nullable=True, index=True)
    schema_version = Column(String(20), nullable=False)
    module = Column(String(30), nullable=False, default="bin_picking", index=True)

    # ── 요약 ──
    n_detections = Column(Integer, nullable=False, default=0)
    n_unique_labels = Column(Integer, nullable=False, default=0)
    recognition_track = Column(String(30), nullable=True)
    latency_ms = Column(Float, nullable=True)

    # ── 게이트 판정 (⭐ 1급 컬럼) ──
    gate_verdict = Column(String(30), nullable=False, default="not_checked", index=True)
    gate_trusted = Column(Boolean, nullable=True)  # None = 판정 없음
    gate_valid_ratio_pct = Column(Float, nullable=True)
    gate_note = Column(Text, nullable=True)
    gate_n_dropped_by_size = Column(Integer, nullable=False, default=0)

    # 모듈이 찍은 시각(문자열 그대로 보존) + 서버 수신 시각
    reported_at = Column(String(40), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self):
        return (f"<BinPickScene {self.scene_id} n={self.n_detections} "
                f"gate={self.gate_verdict}>")


class BinPickDetection(Base):
    """장면 안의 검출 1건 (부품 하나)

    ⭐ 로봇 전용 값(`edge` 4코너·`camera_3d`)은 여기 없다 — 8/7 설계원칙 2.
       웹은 사람이 보는 화면이라 쓸모가 없고 payload만 커진다.
    """
    __tablename__ = "binpick_detections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scene_pk = Column(String(36), nullable=False, index=True)  # BinPickScene.id

    # 장면 안에서의 순서. ⭐ grasp_plan과 인덱스 1:1 대응이 계약이므로 보존한다.
    idx = Column(Integer, nullable=False, default=0)

    label = Column(String(60), nullable=True, index=True)
    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)
    z = Column(Float, nullable=True)
    angle = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    gripper_width_mm = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<BinPickDetection {self.label} @({self.x},{self.y},{self.z})>"


# 최근 장면 조회가 주 패턴이라 복합 인덱스를 둔다.
Index("ix_binpick_scenes_module_created", BinPickScene.module, BinPickScene.created_at)
