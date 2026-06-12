"""
OCR recognition engine module
Uses RapidOCR (ONNXRuntime) for text recognition
"""

import logging
import traceback
import numpy as np
import cv2
from typing import List, Tuple, Optional


class OCREngine:
    """OCR recognition engine backed by RapidOCR / ONNXRuntime"""

    def __init__(self, config: dict):
        self.config = config
        self.use_angle_cls = config.get('use_angle_cls', False)
        self.rec_score_thresh = config.get('rec_score_thresh', 0.5)
        self.det_db_thresh = config.get('det_db_thresh', 0.3)
        self.det_limit_side_len = config.get('det_limit_side_len', 960)
        self.show_detection_boxes = config.get('show_detection_boxes', True)

        self.logger = logging.getLogger(__name__)
        self.engine = None
        self.total_processed = 0
        self.last_det_ms: float = 0.0
        self.last_rec_ms: float = 0.0

    def initialize(self) -> bool:
        try:
            from rapidocr_onnxruntime import RapidOCR

            self.engine = RapidOCR(
                text_score=self.rec_score_thresh,
                use_cls=self.use_angle_cls,
                # limit_type='max' so DetPreProcess.resize honours the side-len cap
                det_limit_type='max',
                det_thresh=self.det_db_thresh,
            )
            # det_limit_side_len is hard-coded by get_preprocess() tiers;
            # we control effective resolution by pre-resizing to 960px in ocr_core.py

            self.logger.info("RapidOCR initialized successfully")
            self.logger.info(f"  Angle cls: {'enabled' if self.use_angle_cls else 'disabled'}")
            self.logger.info(f"  Det thresh: {self.det_db_thresh}")
            self.logger.info(f"  Rec score thresh: {self.rec_score_thresh}")
            return True

        except Exception as e:
            self.logger.error(f"RapidOCR initialization failed: {e}")
            self.logger.error(traceback.format_exc())
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_bgr(self, image: np.ndarray) -> np.ndarray:
        if len(image.shape) == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return image

    def _parse_result(self, raw) -> List[Tuple[List, Tuple[str, float]]]:
        """Convert RapidOCR [[box, text, score], ...] to internal format."""
        if not raw:
            return []
        out = []
        for item in raw:
            box, text, score = item[0], item[1], item[2]
            if score >= self.rec_score_thresh:
                # box is already list-of-points; ensure plain Python floats
                pts = [[float(p[0]), float(p[1])] for p in box]
                out.append((pts, (text, float(score))))
        return out

    # ------------------------------------------------------------------
    # Public API (same interface as original OCREngine)
    # ------------------------------------------------------------------

    def recognize(self, image: np.ndarray) -> List[Tuple[List, Tuple[str, float]]]:
        if self.engine is None:
            self.logger.error("OCR engine not initialized")
            return []
        if image is None:
            return []

        try:
            image = self._to_bgr(image)
            raw, elapse = self.engine(
                image,
                use_cls=self.use_angle_cls,
                text_score=self.rec_score_thresh,
            )
            self.last_det_ms = round((elapse[0] if elapse else 0) * 1000, 1)
            self.last_rec_ms = round((elapse[2] if elapse and len(elapse) > 2 else 0) * 1000, 1)
            self.total_processed += 1
            results = self._parse_result(raw)
            sorted_results = self.sort_results_by_position(results)

            if sorted_results:
                self.logger.info("=" * 60)
                det_ms = self.last_det_ms
                rec_ms = self.last_rec_ms
                self.logger.info(f"OCR results ({len(sorted_results)} items)  det={det_ms}ms rec={rec_ms}ms")
                self.logger.info("=" * 60)
                for i, (_, (text, conf)) in enumerate(sorted_results, 1):
                    self.logger.info(f"  [{i:2d}] {text:<40s} (confidence: {conf:.2f})")
                self.logger.info("=" * 60)
            else:
                self.logger.info("OCR detected no text")

            return sorted_results

        except Exception as e:
            self.logger.error(f"OCR recognition failed: {e}")
            self.logger.error(traceback.format_exc())
            return []

    def recognize_split(self, image: np.ndarray, on_det_done=None) -> List[Tuple[List, Tuple[str, float]]]:
        """Run full pipeline once, then fire on_det_done with the detected boxes.
        (RapidOCR has no native det/rec split, so we avoid running det twice.)"""
        results = self.recognize(image)
        if on_det_done and results:
            on_det_done([box for box, _ in results])
        return results

    def sort_results_by_position(
        self, results: List[Tuple[List, Tuple[str, float]]]
    ) -> List[Tuple[List, Tuple[str, float]]]:
        if not results:
            return results

        def get_sort_key(item):
            box = item[0]
            min_y = min(p[1] for p in box)
            min_x = min(p[0] for p in box)
            max_y = max(p[1] for p in box)
            height = max_y - min_y
            row = int(min_y / max(height * 0.5, 10))
            return (row, min_x)

        return sorted(results, key=get_sort_key)

    def extract_text_only(self, results: List[Tuple[List, Tuple[str, float]]]) -> List[str]:
        return [text for _, (text, _) in results]

    def draw_boxes(self, image: np.ndarray, results: List[Tuple[List, Tuple[str, float]]]) -> np.ndarray:
        if not self.show_detection_boxes or not results:
            return image

        output = self._to_bgr(image.copy())
        for box, (_, confidence) in results:
            points = np.array(box, dtype=np.int32)
            if confidence >= 0.8:
                color = (255, 100, 0)
            elif confidence >= 0.6:
                color = (0, 200, 255)
            else:
                color = (0, 100, 255)
            cv2.polylines(output, [points], isClosed=True, color=color, thickness=1)
        return output

    def get_stats(self) -> dict:
        return {
            'total_processed': self.total_processed,
            'use_angle_cls': self.use_angle_cls,
            'det_db_thresh': self.det_db_thresh,
            'rec_score_thresh': self.rec_score_thresh,
        }

    def set_recognition_threshold(self, threshold: float):
        self.rec_score_thresh = threshold
        if self.engine:
            self.engine.text_score = threshold
        self.logger.info(f"Recognition threshold set: {threshold}")

    def recognize_multi_angle(
        self, image: np.ndarray, image_processor, angles: list = None
    ) -> Tuple[List, float]:
        if angles is None:
            angles = [0, -5, 5, -10, 10, -15, 15, -20, 20]

        best_results, best_angle, best_score = [], 0, 0

        for angle in angles:
            rotated = image if angle == 0 else image_processor.rotate_image(image, angle)
            results = self.recognize(rotated)
            if results:
                avg_conf = sum(c for _, (_, c) in results) / len(results)
                score = len(results) * avg_conf
                if score > best_score:
                    best_score, best_results, best_angle = score, results, angle

        self.logger.info(f"Multi-angle: best angle={best_angle}°, {len(best_results)} items")
        return best_results, best_angle
