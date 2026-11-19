# AgroDrone AI Licensing & Compliance Guide

AgroDrone's baseline computer vision engine (`services/ai-worker`) uses the **Ultralytics YOLO** (`ultralytics`) Python package with the pretrained `yolov8n.pt` checkpoint (MS COCO 2017, 80 general-object classes).

> **Legal Notice:** This document is a technical licensing summary, not formal legal advice. Obtain legal/commercial sign-off before public or commercial SaaS distribution.

---

## 1. Applicable Licenses in the AI Stack

| Component | Package / Artifact | License | Notes |
|---|---|---|---|
| **Ultralytics YOLO** | `ultralytics` | **AGPL-3.0** (or Ultralytics Enterprise License) | Copyleft license with network-interaction clause (Section 13). |
| **PyTorch** | `torch` | BSD-3-Clause | Permissive. |
| **OpenCV** | `opencv-python-headless` | Apache-2.0 | Permissive. |
| **Pillow / NumPy** | `pillow`, `numpy` | HPND / BSD-3-Clause | Permissive. |

---

## 2. Deployment & Usage Obligations

### A. Internal Testing & Local Evaluation
- Running AgroDrone locally on a developer workstation or private internal bench for evaluation, testing, and research is permitted under AGPL-3.0 without requiring public source disclosure to external third parties.

### B. Public Network Deployment (Open-Source AGPL-3.0)
- Under **AGPL-3.0 Section 13**, if a modified or unmodified AGPL-3.0 work is hosted on a network server and **external users interact with it remotely over a network**, you must make the **Complete Corresponding Source Code** of the AgroDrone application (control plane + worker + any integrated modifications) available to those users under AGPL-3.0.

### C. Commercial Proprietary SaaS Deployment
- If you intend to offer AgroDrone as a **closed-source / proprietary commercial SaaS** without releasing the full platform source code under AGPL-3.0:
  - **You MUST obtain a commercial Ultralytics Enterprise License** prior to launch, **OR**
  - Replace the `ultralytics` runtime with a permissively licensed inference runtime (e.g. ONNX Runtime / Apache-2.0 or MIT-licensed weights & inference code).
- **Current Status:** No Ultralytics Enterprise License is on file in this repository; therefore commercial proprietary SaaS clearance is **NOT** asserted.
