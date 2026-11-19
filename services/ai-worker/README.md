# AgroDrone AI Inference Worker (`services/ai-worker`)

**Status:** Active in **Phase 3 (AgroVision AI Engine)**.

## Technology Stack
- **Ultralytics YOLO** (`ultralytics`, pinned official `yolov8n.pt` general baseline)
- **PyTorch** (`torch`, CPU by default, optional CUDA GPU acceleration)
- **OpenCV** (`cv2` for annotated bounding-box rendering and sampled video frame decoding)
- **Pillow** (`PIL` for EXIF-aware image decoding and decompression-bomb protection)
- **NumPy** (`numpy` for tensor/array transformations)

## Responsibilities
1. **Modular Model Registry (`agrovision_worker.registry`):**
   - `yolov8n-coco-general`: Available & SHA-256 checksum verified (`f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`).
   - `agrovision-wildlife-v1`, `agrovision-pest-v1`, `agrovision-disease-v1`: Explicitly reported as `not_available` until domain-trained weights and train/val/test evaluation metrics (precision, recall, mAP@0.5) are registered.
2. **Image Analysis (`analyze_image_bytes`):**
   - Safely decodes uploaded JPEG/PNG/WebP imagery, runs real YOLO object detection, measures latency (`inference_ms`), records model checksum, and generates an emerald-annotated JPEG stored in private storage.
3. **Sampled Video Analysis (`analyze_video_bytes`):**
   - Decodes MP4/WebM/MOV streams via secure temporary files (guaranteed cleanup), enforces duration/resolution/frame caps, runs YOLO on configurable `frame_sample_interval_ms` intervals, records exact `timestamp_ms`, and generates per-frame annotated previews without claiming full-frame processing.

## Standalone CLI Verification

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m agrovision_worker.cli --warm-general
```
