import cv2
import numpy as np
import onnxruntime as ort
import time
from datetime import datetime
import pytz
import os
from ultralytics import YOLO
import threading

# Add NumPy compatibility setting
os.environ['NPY_PROMOTION_STATE'] = 'weak'

# Try to import PaddleOCR, fallback to ONNX only if not available
try:
    from paddleocr import PaddleOCR
    PADDLE_OCR_AVAILABLE = True
except ImportError:
    PADDLE_OCR_AVAILABLE = False
    print("PaddleOCR not available, using ONNX OCR only")

class CameraProcessor:
    def __init__(self, camera_id, camera_type):
        self.camera_id = camera_id
        self.camera_type = camera_type
        self.cap = None
        self.frame = None
        self.lock = threading.Lock()
        self.detector = self._initialize_detector()
        self.last_detection_time = 0
        self.detection_cooldown = 3  # seconds between detections

    def _initialize_detector(self):
        # Initialize YOLO and OCR models
        yolo_model = YOLO("yolov8_license_plate2.pt")
        
        class ONNXOCR:
            def __init__(self):
                self.det_session = ort.InferenceSession("models-ocr/PP-OCRv5_mobile_det_infer.onnx")
                self.rec_session = ort.InferenceSession("models-ocr/en_PP-OCRv4_mobile_rec_infer.onnx")
                with open("models-ocr/en_dict.txt", 'r') as f:
                    self.dictionary = [line.strip() for line in f.readlines()]
                self.det_input_name = self.det_session.get_inputs()[0].name
                self.rec_input_name = self.rec_session.get_inputs()[0].name
            
            def recognize_text(self, image):
                # Improved OCR implementation
                img_tensor = self._preprocess(image)
                outputs = self.rec_session.run(None, {self.rec_input_name: img_tensor})
                preds = outputs[0]
                preds_idx = np.argmax(preds, axis=2)
                # Filter out blank characters (index 0) and invalid indices
                valid_indices = [idx for idx in preds_idx[0] if 0 < idx < len(self.dictionary)]
                text = ''.join([self.dictionary[idx] for idx in valid_indices])
                return text, 0.85  # Return confidence score (improved for ONNX)
            
            def _preprocess(self, image):
                img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                img = cv2.resize(img, (320, 48))
                img = img.astype(np.float32) / 255.0
                img = np.transpose(img, (2, 0, 1))
                return np.expand_dims(img, axis=0)
        
        # Initialize PaddleOCR if available
        paddle_ocr = None
        if PADDLE_OCR_AVAILABLE:
            try:
                paddle_ocr = PaddleOCR(
                    use_textline_orientation=False,
                    lang='en',
                    ocr_version='PP-OCRv3'
                )
            except Exception as e:
                print(f"Failed to initialize PaddleOCR: {e}")
                paddle_ocr = None
        
        return {
            'yolo': yolo_model,
            'paddle_ocr': paddle_ocr,
            'onnx_ocr': ONNXOCR()
        }

    def start_capture(self):
        self.cap = cv2.VideoCapture(self.camera_id)
        while True:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(1)
                continue
                
            with self.lock:
                self.frame = frame.copy()
            
            time.sleep(0.03)  # ~30 FPS

    def generate_frames(self, detection_callback):
        while True:
            with self.lock:
                if self.frame is None:
                    continue
                frame = self.frame.copy()
            
            # Process frame for license plates
            current_time = time.time()
            if current_time - self.last_detection_time > self.detection_cooldown:
                results = self.detector['yolo'].predict(frame, conf=0.5)
                
                for result in results:
                    if hasattr(result, 'boxes') and result.boxes is not None:
                        for box in result.boxes:
                            x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                            plate_img = frame[y1:y2, x1:x2]
                            
                            if plate_img.size > 0:
                                # Try PaddleOCR first (if available)
                                plate_text = ""
                                confidence = 0.0
                                ocr_source = "None"
                                
                                if self.detector['paddle_ocr'] is not None:
                                    try:
                                        # Use PaddleOCR as primary with correct API
                                        paddle_result = self.detector['paddle_ocr'].predict(plate_img)
                                        
                                        # Process results to extract complete text (including multi-line)
                                        plate_text = ""
                                        confidence = 0.0
                                        if paddle_result is not None and len(paddle_result) > 0:
                                            # Extract all text from OCR results for complete license plate
                                            all_texts = []
                                            all_scores = []
                                            
                                            for page_result in paddle_result:
                                                if 'rec_texts' in page_result and 'rec_scores' in page_result:
                                                    texts = page_result['rec_texts']
                                                    scores = page_result['rec_scores']
                                                    all_texts.extend(texts)
                                                    all_scores.extend(scores)
                                            
                                            # Combine all detected text (useful for multi-line license plates)
                                            if all_texts:
                                                plate_text = " ".join(all_texts)
                                                confidence = np.mean(all_scores) if all_scores else 0.0
                                        
                                        if plate_text:
                                            ocr_source = "PaddleOCR"
                                            print(f"Original PaddleOCR: {plate_text} (Confidence: {confidence:.2f})")
                                    except Exception as e:
                                        print(f"PaddleOCR failed: {e}")
                                
                                # Fallback to ONNX OCR if PaddleOCR failed or not available
                                if not plate_text and self.detector['onnx_ocr'] is not None:
                                    try:
                                        onnx_text, onnx_conf = self.detector['onnx_ocr'].recognize_text(plate_img)
                                        if onnx_text:
                                            plate_text, confidence = onnx_text, onnx_conf
                                            ocr_source = "ONNX"
                                            print(f"ONNX PaddleOCR: {plate_text} (Confidence: {confidence:.2f})")
                                    except Exception as e:
                                        print(f"ONNX OCR failed: {e}")
                                
                                # Clean and validate the plate text
                                plate_text = ''.join(c for c in plate_text if c.isalnum()).upper()
                                
                                if len(plate_text) >= 5:  # Valid plate number
                                    self.last_detection_time = current_time
                                    
                                    # Save snapshot
                                    ist_time = datetime.now(pytz.timezone('Asia/Kolkata'))
                                    timestamp = ist_time.strftime("%Y%m%d_%H%M%S")
                                    snapshot_path = f"snapshots/{self.camera_type}/{plate_text}_{timestamp}.jpg"
                                    cv2.imwrite(snapshot_path, plate_img)
                                    
                                    # Callback for database update
                                    detection_callback(plate_text, self.camera_type)
            
            # Encode frame for streaming
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    def release(self):
        if self.cap:
            self.cap.release()