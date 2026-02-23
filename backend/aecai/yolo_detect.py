"""YOLO-based fixture detection for electrical drawings.

Uses ultralytics YOLOv8 to detect fixture oval symbols on floor plans.
Requires fine-tuning on labeled data from the target project.

Workflow:
1. User annotates fixtures using the frontend exemplar tool
2. prepare_training_data() converts annotations to YOLO format
3. train_model() fine-tunes YOLOv8n on the annotations
4. detect_fixtures() runs the trained model on page images
5. Pipeline OCRs detected regions to read fixture codes
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Directory for trained models
_MODELS_DIR = Path(
    os.environ.get("AECAI_MODELS_DIR", str(Path(__file__).parent.parent / "models"))
)
_DEFAULT_MODEL = _MODELS_DIR / "fixture_detector.pt"

_CLASS_NAME = "fixture"


def is_model_available(model_path: str | Path | None = None) -> bool:
    """Check if a trained YOLO model exists."""
    path = Path(model_path) if model_path else _DEFAULT_MODEL
    return path.exists()


def detect_fixtures(
    image: np.ndarray,
    model_path: str | Path | None = None,
    conf: float = 0.25,
    iou: float = 0.45,
    imgsz: int = 1280,
) -> list[dict]:
    """Detect fixture symbols on a floor plan page using YOLO.

    Args:
        image: BGR page image (any resolution)
        model_path: path to trained .pt model
        conf: confidence threshold
        iou: NMS IoU threshold
        imgsz: inference image size (YOLO resizes internally)

    Returns:
        list of detections: {x, y, w, h, confidence}
    """
    from ultralytics import YOLO

    path = Path(model_path) if model_path else _DEFAULT_MODEL
    if not path.exists():
        logger.warning("YOLO model not found at %s — run training first.", path)
        return []

    model = YOLO(str(path))
    results = model.predict(
        source=image,
        conf=conf,
        iou=iou,
        imgsz=imgsz,
        verbose=False,
    )

    detections = []
    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            detections.append({
                "x": int(x1),
                "y": int(y1),
                "w": int(x2 - x1),
                "h": int(y2 - y1),
                "confidence": float(box.conf[0]),
            })

    logger.info("YOLO detected %d fixtures", len(detections))
    return detections


def prepare_training_data(
    pdf_path: str | Path,
    annotations: list[dict],
    output_dir: str | Path | None = None,
    dpi: int = 600,
) -> Path:
    """Convert user annotations to YOLO training format.

    Annotations come from the frontend exemplar tool:
        [{page, x, y, w, h, source_dpi, label}]

    Creates the standard YOLO directory layout:
        output_dir/
            images/train/
            labels/train/
            dataset.yaml

    Returns path to dataset.yaml.
    """
    import PIL.Image
    from pdf2image import convert_from_path

    from .config import POPPLER_PATH

    PIL.Image.MAX_IMAGE_PIXELS = 250_000_000

    output = Path(output_dir or tempfile.mkdtemp(prefix="aecai_yolo_"))
    img_dir = output / "images" / "train"
    lbl_dir = output / "labels" / "train"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    by_page: dict[int, list[dict]] = defaultdict(list)
    for ann in annotations:
        by_page[ann["page"]].append(ann)

    for page_num, page_anns in by_page.items():
        kwargs: dict[str, Any] = {
            "dpi": dpi,
            "first_page": page_num,
            "last_page": page_num,
        }
        if POPPLER_PATH:
            kwargs["poppler_path"] = POPPLER_PATH

        pil_images = convert_from_path(str(pdf_path), **kwargs)
        if not pil_images:
            continue

        img_path = img_dir / f"page_{page_num}.jpg"
        pil_images[0].save(str(img_path), "JPEG", quality=95)

        img_w, img_h = pil_images[0].size

        # YOLO format: class_id center_x center_y width height (normalised 0-1)
        label_path = lbl_dir / f"page_{page_num}.txt"
        with open(label_path, "w") as f:
            for ann in page_anns:
                source_dpi = ann.get("source_dpi", 150)
                scale = dpi / source_dpi

                ax = ann["x"] * scale
                ay = ann["y"] * scale
                aw = ann["w"] * scale
                ah = ann["h"] * scale

                cx = max(0.0, min(1.0, (ax + aw / 2) / img_w))
                cy = max(0.0, min(1.0, (ay + ah / 2) / img_h))
                nw = max(0.0, min(1.0, aw / img_w))
                nh = max(0.0, min(1.0, ah / img_h))

                f.write(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")

        logger.info(
            "Created training data for page %d: %d annotations",
            page_num, len(page_anns),
        )

    yaml_path = output / "dataset.yaml"
    yaml_path.write_text(
        f"path: {output}\n"
        f"train: images/train\n"
        f"val: images/train\n"  # reuse train for small datasets
        f"\n"
        f"nc: 1\n"
        f"names: ['{_CLASS_NAME}']\n"
    )

    logger.info("Training data prepared at %s", output)
    return yaml_path


def train_model(
    dataset_yaml: str | Path,
    epochs: int = 50,
    imgsz: int = 1280,
    batch: int = 2,
    base_model: str = "yolov8n.pt",
    output_path: str | Path | None = None,
    progress_callback=None,
) -> Path:
    """Fine-tune YOLOv8 on fixture detection data.

    Args:
        dataset_yaml: path to dataset.yaml
        epochs: training epochs
        imgsz: training image size
        batch: batch size (keep small for large images)
        base_model: pre-trained model to fine-tune from
        output_path: where to save the trained model
        progress_callback: optional (epoch, total_epochs) callback

    Returns:
        Path to the trained model file.
    """
    from ultralytics import YOLO

    model = YOLO(base_model)

    results = model.train(
        data=str(dataset_yaml),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device="cpu",
        project=str(_MODELS_DIR / "runs"),
        name="fixture_detector",
        exist_ok=True,
        verbose=True,
    )

    save_path = Path(output_path) if output_path else _DEFAULT_MODEL
    save_path.parent.mkdir(parents=True, exist_ok=True)

    best = Path(results.save_dir) / "weights" / "best.pt"
    if best.exists():
        shutil.copy2(best, save_path)
        logger.info("Trained model saved to %s", save_path)
    else:
        last = Path(results.save_dir) / "weights" / "last.pt"
        if last.exists():
            shutil.copy2(last, save_path)
            logger.info("Trained model (last) saved to %s", save_path)

    return save_path


def generate_annotations_from_ovals(
    pdf_path: str | Path,
    pages: list[int],
    dpi: int = 600,
) -> list[dict]:
    """Bootstrap training annotations using the existing oval detector.

    Runs the calibrated contour-based oval detector on specified pages
    and returns annotations suitable for prepare_training_data().
    These should be manually reviewed before training.
    """
    import gc

    from .pipeline import _render_single_page
    from .shapes import find_ovals

    annotations = []
    for page_num in pages:
        image = _render_single_page(pdf_path, page_num, dpi=dpi)
        if image is None:
            continue

        ovals = find_ovals(image)
        for oval in ovals:
            annotations.append({
                "page": page_num,
                "x": oval["x"],
                "y": oval["y"],
                "w": oval["w"],
                "h": oval["h"],
                "source_dpi": dpi,
                "label": "fixture",
            })

        logger.info("Auto-annotated page %d: %d ovals", page_num, len(ovals))
        del image
        gc.collect()

    return annotations
