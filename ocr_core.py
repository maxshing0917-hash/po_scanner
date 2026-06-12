# -*- coding: utf-8 -*-
"""
PO Scanner OCR Worker — stdin/stdout newline-delimited JSON protocol.

Startup
  main → worker  line 1 : JSON config dict
  worker → main          : {"type": "ready", "ok": true|false}

Per scan
  main → worker  : {"action": "recognize", "image_path": "...", "det_image_path": "...", "pre_config": {...}}
  worker → main  : {"type": "det_done"}          (det image written to det_image_path)
  worker → main  : {"type": "result", ...fields} (final extraction result)

Shutdown
  main → worker  : {"action": "quit"}
"""

import sys
import os
import json

os.environ['ORT_DISABLE_ALL_LOGS'] = '1'

import logging

import cv2
import numpy as np
import time


def _send(obj: dict):
    sys.stdout.write(json.dumps(obj) + '\n')
    sys.stdout.flush()


def main():
    cfg_line = sys.stdin.readline()
    if not cfg_line:
        return
    config = json.loads(cfg_line)

    log_path = os.path.join(os.path.expanduser('~'), 'po_scanner_worker.log')
    try:
        import logging as _lg
        fh = _lg.FileHandler(log_path, mode='w', encoding='utf-8')
        fh.setLevel(_lg.DEBUG)
        _lg.getLogger().addHandler(fh)
        _lg.getLogger('src.ocr.ocr_engine').setLevel(_lg.DEBUG)

        from src.ocr.ocr_engine import OCREngine
        engine = OCREngine(config.get('ocr', {}))
        ok = engine.initialize()
        if ok:
            # Warm up ONNX/CUDA JIT — must actually detect+recognize text so both
            # det and rec kernels are compiled before the first real scan.
            _w = np.ones((480, 640, 3), dtype=np.uint8) * 240
            cv2.putText(_w, 'PO 123456789', (40, 180), cv2.FONT_HERSHEY_DUPLEX, 3, (20, 20, 20), 6)
            cv2.putText(_w, '1Z999AA10123456784', (40, 320), cv2.FONT_HERSHEY_DUPLEX, 1.4, (20, 20, 20), 3)
            cv2.putText(_w, '420 12345 9400111899223397906071', (40, 420), cv2.FONT_HERSHEY_DUPLEX, 0.9, (20, 20, 20), 2)
            engine.recognize(_w)
    except Exception as e:
        _send({'type': 'ready', 'ok': False, 'error': str(e)})
        return

    _send({'type': 'ready', 'ok': ok})
    if not ok:
        return

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            req = json.loads(line)
        except Exception:
            continue

        action = req.get('action')
        if action == 'quit':
            break
        elif action == 'recognize':
            try:
                _handle_recognize(engine, req, config)
            except Exception as e:
                _send({'type': 'error', 'message': str(e)})


def _handle_recognize(engine, req: dict, config: dict):
    from src.preprocessing.image_processor import ImageProcessor
    from src.utils.extractor import (
        extract_po, extract_tracking,
        detect_carrier_from_keywords,
    )

    image_path   = req['image_path']
    det_img_path = req.get('det_image_path', image_path + '_det.jpg')
    pre_config   = req.get('pre_config', config.get('preprocessing', {}))
    blacklist    = req.get('blacklist', config.get('extraction', {}).get('po_blacklist', []))

    t0 = time.perf_counter()

    img = cv2.imread(image_path)
    if img is None:
        _send({'type': 'error', 'message': f'Cannot read image: {image_path}'})
        return

    # Resize if too large
    h, w = img.shape[:2]
    t_resize0 = time.perf_counter()
    if max(h, w) > 960:
        scale = 960 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    resize_ms = (time.perf_counter() - t_resize0) * 1000

    # Preprocessing
    t_preproc0 = time.perf_counter()
    proc      = ImageProcessor(pre_config)
    processed = proc.process(img)
    if processed is None:
        processed = img
    preproc_ms = (time.perf_counter() - t_preproc0) * 1000

    # Detection callback — draw boxes on original image and notify main
    def _on_det(boxes):
        display = img.copy()
        if len(display.shape) == 2:
            display = cv2.cvtColor(display, cv2.COLOR_GRAY2BGR)
        for box in boxes:
            pts = np.array(box, dtype=np.int32)
            cv2.polylines(display, [pts], isClosed=True, color=(0, 200, 0), thickness=2)
        cv2.imwrite(det_img_path, display)
        _send({'type': 'det_done'})

    t_ocr0 = time.perf_counter()
    results = engine.recognize_split(processed, on_det_done=_on_det)
    ocr_ms  = (time.perf_counter() - t_ocr0) * 1000
    trk_candidates = []

    # PO / tracking extraction
    t_po0 = time.perf_counter()
    lines            = [text for _, (text, _) in results]
    po_candidates, po_source = extract_po(lines, blacklist=blacklist)
    po               = po_candidates[0] if len(po_candidates) == 1 else None
    ocr_carrier      = detect_carrier_from_keywords(lines)

    if not trk_candidates:
        ocr_trk, ocr_trk_source = extract_tracking(lines)
        if not ocr_trk and ocr_carrier:
            ocr_trk, ocr_trk_source = extract_tracking(lines, forced_carrier=ocr_carrier)
        if ocr_trk:
            trk_candidates = [(ocr_trk, ocr_trk_source)]
    po_extract_ms = (time.perf_counter() - t_po0) * 1000

    tracking   = trk_candidates[0][0] if trk_candidates else ''
    trk_source = trk_candidates[0][1] if trk_candidates else ''

    total_ms = (time.perf_counter() - t0) * 1000
    det_ms = engine.last_det_ms
    rec_ms = engine.last_rec_ms
    ocr_overhead_ms = ocr_ms - det_ms - rec_ms
    _send({'type': 'log', 'msg': (
        f'[TIMING] resize={resize_ms:.1f}ms | preproc={preproc_ms:.1f}ms'
        f' | OCR={ocr_ms:.1f}ms (det={det_ms:.1f}ms rec={rec_ms:.1f}ms overhead={ocr_overhead_ms:.1f}ms)'
        f' | po_extract={po_extract_ms:.1f}ms | TOTAL={total_ms:.1f}ms'
    )})

    _send({
        'type':                'result',
        'po':                  po or '',
        'po_candidates':       po_candidates,
        'po_source':           po_source,
        'tracking':            tracking,
        'tracking_candidates': [list(t) for t in trk_candidates],
        'tracking_source':     trk_source,
        'ocr_carrier':         ocr_carrier or '',
    })


if __name__ == '__main__':
    main()
