"""
동영상에서 학습용 프레임 추출
- 1초 간격으로 프레임 추출
- 240x240 리사이즈 (OpenMV AE3 입력 크기)
- 라벨별 폴더로 분류
"""

import cv2
import os
from pathlib import Path

# 동영상 → 라벨 매핑
VIDEO_LABEL_MAP = {
    "세척기 시작전.mp4": "wash_idle",
    "세척기 동작중.mp4": "wash_running",
    "세척기 완료.mp4": "wash_complete",
    "경화기 시작전.mp4": "cure_idle",
    "경화기 동작중.mp4": "cure_running",
    "경화기 완료.mp4": "cure_complete",
}

VIDEO_DIR = Path(__file__).parent / "training_videos"
OUTPUT_DIR = Path(__file__).parent / "training_images"
TARGET_SIZE = (240, 240)  # OpenMV AE3 입력 크기
FRAME_INTERVAL_SEC = 0.5  # 0.5초 간격 (더 많은 이미지 확보)


def extract_frames(video_path: Path, label: str, output_dir: Path):
    """동영상에서 프레임 추출"""
    label_dir = output_dir / label
    label_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"  ❌ 열 수 없음: {video_path.name}")
        return 0

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    frame_skip = int(fps * FRAME_INTERVAL_SEC)

    print(f"  📹 {video_path.name}: {duration:.1f}초, {fps:.0f}fps, {total_frames}프레임")

    count = 0
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_skip == 0:
            # 정사각형 크롭 (중앙)
            h, w = frame.shape[:2]
            min_dim = min(h, w)
            start_x = (w - min_dim) // 2
            start_y = (h - min_dim) // 2
            cropped = frame[start_y:start_y + min_dim, start_x:start_x + min_dim]

            # 리사이즈
            resized = cv2.resize(cropped, TARGET_SIZE, interpolation=cv2.INTER_AREA)

            # 저장
            filename = f"{label}_{count:04d}.jpg"
            cv2.imwrite(str(label_dir / filename), resized, [cv2.IMWRITE_JPEG_QUALITY, 95])
            count += 1

        frame_idx += 1

    cap.release()
    return count


def main():
    print("=" * 50)
    print("동영상 → 학습 이미지 프레임 추출")
    print(f"입력: {VIDEO_DIR}")
    print(f"출력: {OUTPUT_DIR}")
    print(f"크기: {TARGET_SIZE[0]}x{TARGET_SIZE[1]}")
    print(f"간격: {FRAME_INTERVAL_SEC}초")
    print("=" * 50)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0

    for video_name, label in VIDEO_LABEL_MAP.items():
        video_path = VIDEO_DIR / video_name
        if not video_path.exists():
            print(f"  ⚠️ 파일 없음: {video_name}")
            continue

        count = extract_frames(video_path, label, OUTPUT_DIR)
        print(f"  ✅ {label}: {count}장 추출")
        total += count

    print("=" * 50)
    print(f"총 {total}장 추출 완료!")
    print()

    # 라벨별 통계
    for label_dir in sorted(OUTPUT_DIR.iterdir()):
        if label_dir.is_dir():
            count = len(list(label_dir.glob("*.jpg")))
            print(f"  {label_dir.name}: {count}장")


if __name__ == "__main__":
    main()
