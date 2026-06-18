"""
Preprocessing module
Handles ROI cropping, image enhancement, and deskew

These steps run before OCR to improve character recognition accuracy
on camera captures of physical package labels (low contrast, skew, noise).
"""

import cv2
import numpy as np
import logging
from typing import Optional, Tuple


class ImageProcessor:
    """Image preprocessing class"""

    def __init__(self, config: dict):
        """
        Initialize image processor

        Args:
            config: configuration dictionary
        """
        self.config = config
        self.roi = config.get('roi', None)  # (x, y, width, height)
        self.enable_grayscale = config.get('enable_grayscale', True)
        self.enable_contrast = config.get('enable_contrast', True)
        self.contrast_factor = config.get('contrast_factor', 1.5)
        self.enable_denoise = config.get('enable_denoise', True)
        self.denoise_strength = config.get('denoise_strength', 3)
        self.enable_sharpen = config.get('enable_sharpen', False)
        self.sharpen_strength = config.get('sharpen_strength', 1.5)
        self.scale_factor = config.get('scale_factor', 1.0)
        self.enable_deskew = config.get('enable_deskew', True)

        # Advanced enhancement options
        self.enable_binarization = config.get('enable_binarization', True)
        self.enable_background_removal = config.get('enable_background_removal', False)

        self.logger = logging.getLogger(__name__)
        self.last_skew_angle = 0.0  # last detected skew angle

    def process(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Process an image frame

        Args:
            frame: input image

        Returns:
            processed image, or None if processing failed
        """
        if frame is None:
            return None

        try:
            # 1. ROI crop
            if self.roi:
                frame = self._crop_roi(frame)

            # 2. Scale
            if self.scale_factor != 1.0:
                frame = self._resize(frame)

            # 3. Auto deskew
            if self.enable_deskew:
                frame = self._deskew(frame)

            # 5. Grayscale conversion
            if self.enable_grayscale:
                frame = self._convert_to_grayscale(frame)

            # 6. Denoise
            if self.enable_denoise:
                frame = self._denoise(frame)

            # 6.5. Sharpen (after denoise, before contrast enhancement)
            if self.enable_sharpen:
                frame = self._sharpen(frame)

            # 7. Contrast enhancement
            if self.enable_contrast:
                frame = self._enhance_contrast(frame)

            # 8. Background removal (text only)
            if self.enable_background_removal and len(frame.shape) == 2:
                frame = self._remove_background(frame)

            # 9. Smart binarization (last step before OCR)
            if self.enable_binarization and len(frame.shape) == 2:
                frame = self._smart_binarization(frame)

            return frame

        except Exception as e:
            self.logger.error(f"Image processing failed: {e}")
            return None

    def _crop_roi(self, frame: np.ndarray) -> np.ndarray:
        """Crop ROI region"""
        x, y, w, h = self.roi
        return frame[y:y+h, x:x+w]

    def _resize(self, frame: np.ndarray) -> np.ndarray:
        """Scale image"""
        new_width = int(frame.shape[1] * self.scale_factor)
        new_height = int(frame.shape[0] * self.scale_factor)
        return cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)

    def _convert_to_grayscale(self, frame: np.ndarray) -> np.ndarray:
        """Convert to grayscale"""
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def _denoise(self, frame: np.ndarray) -> np.ndarray:
        """Denoise using medianBlur — fast and effective for printed label noise."""
        ksize = 3 if self.denoise_strength <= 5 else 5
        return cv2.medianBlur(frame, ksize)

    def _sharpen(self, frame: np.ndarray) -> np.ndarray:
        """
        Sharpen image - enhances edges for clearer small text

        Uses Unsharp Masking:
        1. Create blurred version
        2. original - blurred = edge detail
        3. original + edge detail * strength = sharpened

        Args:
            frame: input image

        Returns:
            sharpened image
        """
        # Create slightly blurred version (Gaussian blur)
        blurred = cv2.GaussianBlur(frame, (0, 0), 3)

        # Compute sharpened image via addWeighted (handles negatives safely)
        sharpened = cv2.addWeighted(
            frame, 1.0 + self.sharpen_strength,  # original weight
            blurred, -self.sharpen_strength,      # blurred weight (negative)
            0  # offset
        )

        return sharpened

    def _enhance_contrast(self, frame: np.ndarray) -> np.ndarray:
        """
        Contrast enhancement using CLAHE
        (Contrast Limited Adaptive Histogram Equalization)
        """
        if len(frame.shape) == 2:  # grayscale
            clahe = cv2.createCLAHE(clipLimit=self.contrast_factor, tileGridSize=(8, 8))
            return clahe.apply(frame)
        else:  # color — apply CLAHE to L channel in LAB color space
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=self.contrast_factor, tileGridSize=(8, 8))
            l = clahe.apply(l)
            enhanced = cv2.merge([l, a, b])
            return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    def _detect_skew_angle(self, frame: np.ndarray) -> float:
        """
        Detect text skew angle using Hough line detection

        Args:
            frame: input image

        Returns:
            float: skew angle in degrees
        """
        # Convert to grayscale
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()

        # Edge detection
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        # Dilate edges to improve line continuity
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)

        # Hough line detection
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=100,
            minLineLength=50,
            maxLineGap=10
        )

        if lines is None or len(lines) == 0:
            # Fallback: use contour method
            return self._detect_skew_by_contours(gray)

        # Calculate angle of each line
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 - x1 == 0:
                continue
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))

            # Only consider near-horizontal lines (text rows are typically horizontal)
            # angle range -45 to 45 degrees
            if -45 <= angle <= 45:
                angles.append(angle)

        if not angles:
            return self._detect_skew_by_contours(gray)

        # Use median to avoid outlier influence
        median_angle = np.median(angles)

        # Ignore very small angles
        if abs(median_angle) < 0.5:
            return 0.0

        return median_angle

    def _detect_skew_by_contours(self, gray: np.ndarray) -> float:
        """
        Fallback: detect skew angle using contours

        Args:
            gray: grayscale image

        Returns:
            float: skew angle
        """
        # Binarize
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return 0.0

        # Keep only larger contours (filter noise)
        min_area = 100
        filtered_contours = [c for c in contours if cv2.contourArea(c) > min_area]

        if not filtered_contours:
            return 0.0

        # Calculate angle for each contour
        angles = []
        for contour in filtered_contours:
            if len(contour) < 5:
                continue
            rect = cv2.minAreaRect(contour)
            angle = rect[-1]

            # Normalize angle range
            if angle < -45:
                angle = 90 + angle
            elif angle > 45:
                angle = angle - 90

            angles.append(angle)

        if not angles:
            return 0.0

        median_angle = np.median(angles)

        if abs(median_angle) < 0.5:
            return 0.0

        return median_angle

    def _deskew(self, frame: np.ndarray) -> np.ndarray:
        """
        Auto-correct image skew

        Args:
            frame: input image

        Returns:
            corrected image
        """
        try:
            angle = self._detect_skew_angle(frame)
            self.last_skew_angle = angle

            # No rotation needed for zero or very small angles
            if abs(angle) < 1.0:
                self.last_skew_angle = 0.0
                return frame

            # Skip correction if angle is too large (likely a detection error)
            if abs(angle) > 30:
                self.logger.warning(f"Detected angle {angle:.2f}° is too large, skipping auto-correction")
                self.last_skew_angle = 0.0
                return frame

            self.logger.info(f"Detected skew angle: {angle:.2f}°, correcting...")

            height, width = frame.shape[:2]
            center = (width // 2, height // 2)

            # Rotation matrix (counter-rotate to correct skew)
            rotation_matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)

            # Compute new bounding box size
            cos = np.abs(rotation_matrix[0, 0])
            sin = np.abs(rotation_matrix[0, 1])
            new_width = int((height * sin) + (width * cos))
            new_height = int((height * cos) + (width * sin))

            # Adjust rotation matrix
            rotation_matrix[0, 2] += (new_width / 2) - center[0]
            rotation_matrix[1, 2] += (new_height / 2) - center[1]

            # Apply rotation (white background fill)
            if len(frame.shape) == 3:
                border_color = (255, 255, 255)
            else:
                border_color = 255

            rotated = cv2.warpAffine(
                frame,
                rotation_matrix,
                (new_width, new_height),
                flags=cv2.INTER_CUBIC,  # high-quality interpolation
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=border_color
            )

            return rotated

        except Exception as e:
            self.logger.error(f"Deskew failed: {e}")
            return frame

    def get_last_skew_angle(self) -> float:
        """Get the last detected skew angle"""
        return self.last_skew_angle

    def rotate_image(self, frame: np.ndarray, angle: float, crop_border: bool = True) -> np.ndarray:
        """
        Rotate image by a given angle

        Args:
            frame: input image
            angle: rotation angle in degrees
            crop_border: whether to crop the border introduced by rotation

        Returns:
            rotated image
        """
        if abs(angle) < 0.1:
            return frame

        height, width = frame.shape[:2]
        center = (width // 2, height // 2)

        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

        cos = np.abs(rotation_matrix[0, 0])
        sin = np.abs(rotation_matrix[0, 1])
        new_width = int((height * sin) + (width * cos))
        new_height = int((height * cos) + (width * sin))

        rotation_matrix[0, 2] += (new_width / 2) - center[0]
        rotation_matrix[1, 2] += (new_height / 2) - center[1]

        # White background (avoids black border interfering with OCR)
        if len(frame.shape) == 3:
            border_color = (255, 255, 255)
        else:
            border_color = 255

        rotated = cv2.warpAffine(
            frame,
            rotation_matrix,
            (new_width, new_height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=border_color
        )

        # Crop border, keep original content region
        if crop_border:
            rotated = self._crop_rotated_image(rotated, width, height, angle)

        return rotated

    def _crop_rotated_image(self, rotated: np.ndarray, orig_width: int,
                            orig_height: int, angle: float) -> np.ndarray:
        """
        Crop rotated image to remove border regions.
        Tries content detection first, falls back to geometric calculation.
        """
        # Try content region detection
        content_crop = self._detect_content_region(rotated)
        if content_crop is not None:
            return content_crop

        # Fallback: geometric calculation
        angle_rad = np.abs(np.radians(angle))

        if angle_rad == 0:
            return rotated

        cos_a = np.cos(angle_rad)
        sin_a = np.sin(angle_rad)

        if orig_width <= 2 * sin_a * cos_a * orig_height or \
           orig_height <= 2 * sin_a * cos_a * orig_width:
            scale = cos_a
            crop_width = int(orig_width * scale)
            crop_height = int(orig_height * scale)
        else:
            cos2_a = cos_a * cos_a
            sin2_a = sin_a * sin_a
            crop_width = int((orig_width * cos_a - orig_height * sin_a) / (cos2_a - sin2_a) * cos_a)
            crop_height = int((orig_height * cos_a - orig_width * sin_a) / (cos2_a - sin2_a) * cos_a)
            crop_width = min(crop_width, orig_width)
            crop_height = min(crop_height, orig_height)

        crop_width = max(crop_width, int(orig_width * 0.5))
        crop_height = max(crop_height, int(orig_height * 0.5))

        rot_height, rot_width = rotated.shape[:2]
        x = (rot_width - crop_width) // 2
        y = (rot_height - crop_height) // 2
        x = max(0, x)
        y = max(0, y)
        x2 = min(rot_width, x + crop_width)
        y2 = min(rot_height, y + crop_height)

        return rotated[y:y2, x:x2]

    def _detect_content_region(self, image: np.ndarray) -> Optional[np.ndarray]:
        """
        Detect the main content region (non-border area) of an image

        Args:
            image: input image

        Returns:
            cropped image, or None if detection failed
        """
        try:
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()

            # Binarize: find non-border region
            # Border is assumed to be pure black (<30) or pure white (>225)
            mask = cv2.inRange(gray, 30, 225)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return None

            # Find largest contour (assumed to be main content)
            largest = max(contours, key=cv2.contourArea)

            x, y, w, h = cv2.boundingRect(largest)

            # Ensure region is large enough (at least 20% of image area)
            img_area = image.shape[0] * image.shape[1]
            content_area = w * h

            if content_area < img_area * 0.2:
                return None

            # Add small padding
            padding = 5
            x = max(0, x - padding)
            y = max(0, y - padding)
            w = min(image.shape[1] - x, w + padding * 2)
            h = min(image.shape[0] - y, h + padding * 2)

            return image[y:y+h, x:x+w]

        except Exception as e:
            self.logger.error(f"Content region detection failed: {e}")
            return None

    def set_roi(self, x: int, y: int, width: int, height: int):
        """Dynamically set ROI"""
        self.roi = (x, y, width, height)
        self.logger.info(f"ROI set: {self.roi}")

    def clear_roi(self):
        """Clear ROI"""
        self.roi = None
        self.logger.info("ROI cleared")

    def get_processing_stats(self) -> dict:
        """Get processing statistics"""
        return {
            'roi': self.roi,
            'grayscale': self.enable_grayscale,
            'contrast': self.enable_contrast,
            'denoise': self.enable_denoise,
            'deskew': self.enable_deskew,
            'last_skew_angle': self.last_skew_angle,
            'scale_factor': self.scale_factor
        }

    # =============== Advanced image enhancement methods ===============

    def _remove_background(self, image: np.ndarray) -> np.ndarray:
        """
        Background removal - keep only text (suitable for cluttered backgrounds)

        Method:
        1. Estimate background using large-kernel morphological opening
        2. Subtract background, keep foreground (text)
        3. Binarize

        Args:
            image: input image (grayscale)

        Returns:
            binary image with background removed
        """
        try:
            # Estimate background (large-kernel morphological opening)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (60, 60))
            background = cv2.morphologyEx(image, cv2.MORPH_OPEN, kernel)

            # Subtract background
            foreground = cv2.subtract(image, background)

            # Binarize
            _, binary = cv2.threshold(foreground, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            self.logger.debug("Background removal complete")
            return binary

        except Exception as e:
            self.logger.warning(f"Background removal failed: {e}, using original")
            return image

    def _smart_binarization(self, image: np.ndarray) -> np.ndarray:
        """
        Binarization using Adaptive Gaussian — handles uneven lighting and
        colored box backgrounds that shipping labels are typically attached to.
        """
        try:
            return cv2.adaptiveThreshold(
                image, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=15,
                C=3
            )
        except Exception as e:
            self.logger.warning(f"Binarization failed: {e}, using original")
            return image
