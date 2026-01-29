"""Screenshot capture backends for AI intervention system.

This module provides screenshot capture functionality with multiple backends:
- MSSBackend: Pure Python, cross-platform (recommended)
- ScrotBackend: X11 fallback using scrot command

The screenshots are optimized for API submission (JPEG compression, size limits).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional, Tuple
import base64
import logging
import subprocess
import time

logger = logging.getLogger(__name__)


class ScreenshotError(Exception):
    """Exception raised when screenshot capture fails."""

    def __init__(self, message: str, backend: Optional[str] = None):
        """Initialize the error.

        Args:
            message: Error description.
            backend: Name of the backend that failed.
        """
        self.backend = backend
        super().__init__(message)


@dataclass
class Screenshot:
    """Captured screenshot with metadata.

    Attributes:
        image_data: Raw image bytes (JPEG or PNG).
        media_type: MIME type ("image/jpeg" or "image/png").
        width: Image width in pixels.
        height: Image height in pixels.
        timestamp: Unix timestamp when captured.
    """
    image_data: bytes
    media_type: str
    width: int
    height: int
    timestamp: float

    def to_base64(self) -> str:
        """Encode image as base64 for API submission.

        Returns:
            Base64-encoded string of image data.
        """
        return base64.b64encode(self.image_data).decode('utf-8')

    def save(self, path: Path) -> None:
        """Save screenshot to file for debugging.

        Args:
            path: File path to save to. Extension should match media_type.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.image_data)
        logger.debug(f"Screenshot saved to {path} ({len(self.image_data)} bytes)")

    @property
    def size_kb(self) -> float:
        """Get image size in kilobytes."""
        return len(self.image_data) / 1024


class ScreenshotBackend(ABC):
    """Abstract base class for screenshot capture backends."""

    @abstractmethod
    def capture_screen(self) -> Screenshot:
        """Capture the entire screen.

        Returns:
            Screenshot object with image data and metadata.

        Raises:
            ScreenshotError: If capture fails.
        """
        pass

    @abstractmethod
    def capture_window(self, window_id: str) -> Screenshot:
        """Capture a specific window by ID.

        Args:
            window_id: X11 window ID to capture.

        Returns:
            Screenshot object with image data and metadata.

        Raises:
            ScreenshotError: If capture fails.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available on the system.

        Returns:
            True if the backend can be used.
        """
        pass


class MSSBackend(ScreenshotBackend):
    """Screenshot backend using mss (pure Python, cross-platform).

    This is the preferred backend as it's fast (~60fps) and has no external
    dependencies beyond the mss Python package.
    """

    def __init__(
        self,
        jpeg_quality: int = 85,
        max_dimension: int = 1920,
    ):
        """Initialize the MSS backend.

        Args:
            jpeg_quality: JPEG compression quality (1-100).
            max_dimension: Maximum width/height; larger images are scaled.
        """
        self.jpeg_quality = jpeg_quality
        self.max_dimension = max_dimension
        self._mss = None
        self._pil_available = False

        # Check for required libraries
        try:
            import mss
            self._mss_module = mss
        except ImportError:
            self._mss_module = None

        try:
            from PIL import Image
            self._pil_image = Image
            self._pil_available = True
        except ImportError:
            self._pil_image = None

    def is_available(self) -> bool:
        """Check if mss and PIL are available."""
        return self._mss_module is not None and self._pil_available

    def _get_mss(self):
        """Get or create MSS instance."""
        if self._mss is None:
            if self._mss_module is None:
                raise ScreenshotError(
                    "mss library not installed. Install with: pip install mss",
                    backend="mss"
                )
            self._mss = self._mss_module.mss()
        return self._mss

    def _optimize_image(
        self,
        raw_data: bytes,
        width: int,
        height: int,
    ) -> Tuple[bytes, str, int, int]:
        """Optimize screenshot for API submission.

        Converts to JPEG and optionally resizes for smaller payload.

        Args:
            raw_data: Raw BGRA image data from mss.
            width: Original width.
            height: Original height.

        Returns:
            Tuple of (image_data, media_type, final_width, final_height).
        """
        if not self._pil_available:
            raise ScreenshotError(
                "Pillow library not installed. Install with: pip install Pillow",
                backend="mss"
            )

        # Create PIL Image from raw BGRA data
        img = self._pil_image.frombytes('RGB', (width, height), raw_data, 'raw', 'BGRX')

        # Resize if larger than max dimension
        if width > self.max_dimension or height > self.max_dimension:
            ratio = min(self.max_dimension / width, self.max_dimension / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            img = img.resize((new_width, new_height), self._pil_image.Resampling.LANCZOS)
            width, height = new_width, new_height
            logger.debug(f"Resized screenshot to {width}x{height}")

        # Convert to JPEG
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=self.jpeg_quality, optimize=True)
        jpeg_data = buffer.getvalue()

        return jpeg_data, 'image/jpeg', width, height

    def capture_screen(self) -> Screenshot:
        """Capture the entire primary screen.

        Returns:
            Screenshot object with JPEG image data.

        Raises:
            ScreenshotError: If capture fails.
        """
        try:
            sct = self._get_mss()

            # Capture primary monitor (index 1; 0 is "all monitors")
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

            # Grab the screen
            sct_img = sct.grab(monitor)

            # Optimize for API
            image_data, media_type, width, height = self._optimize_image(
                sct_img.rgb,
                sct_img.width,
                sct_img.height,
            )

            return Screenshot(
                image_data=image_data,
                media_type=media_type,
                width=width,
                height=height,
                timestamp=time.time(),
            )

        except Exception as e:
            if isinstance(e, ScreenshotError):
                raise
            raise ScreenshotError(f"Failed to capture screen: {e}", backend="mss") from e

    def capture_window(self, window_id: str) -> Screenshot:
        """Capture a specific window by ID.

        Gets window geometry via xdotool and captures that region.

        Args:
            window_id: X11 window ID.

        Returns:
            Screenshot object with JPEG image data.

        Raises:
            ScreenshotError: If capture fails.
        """
        try:
            # Get window geometry using xdotool
            result = subprocess.run(
                ['xdotool', 'getwindowgeometry', '--shell', window_id],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                raise ScreenshotError(
                    f"Failed to get window geometry: {result.stderr}",
                    backend="mss"
                )

            # Parse geometry output
            geometry: Dict[str, int] = {}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    geometry[key] = int(value)

            x = geometry.get('X', 0)
            y = geometry.get('Y', 0)
            width = geometry.get('WIDTH', 1920)
            height = geometry.get('HEIGHT', 1080)

            # Capture the window region
            sct = self._get_mss()
            monitor = {
                'left': x,
                'top': y,
                'width': width,
                'height': height,
            }
            sct_img = sct.grab(monitor)

            # Optimize for API
            image_data, media_type, final_w, final_h = self._optimize_image(
                sct_img.rgb,
                sct_img.width,
                sct_img.height,
            )

            return Screenshot(
                image_data=image_data,
                media_type=media_type,
                width=final_w,
                height=final_h,
                timestamp=time.time(),
            )

        except subprocess.TimeoutExpired:
            raise ScreenshotError(
                "Timeout getting window geometry",
                backend="mss"
            )
        except Exception as e:
            if isinstance(e, ScreenshotError):
                raise
            raise ScreenshotError(
                f"Failed to capture window: {e}",
                backend="mss"
            ) from e


class ScrotBackend(ScreenshotBackend):
    """Screenshot backend using scrot (X11 command-line tool).

    This is a fallback backend for systems where mss doesn't work well.
    Requires scrot to be installed: sudo apt install scrot
    """

    def __init__(
        self,
        jpeg_quality: int = 85,
        max_dimension: int = 1920,
    ):
        """Initialize the scrot backend.

        Args:
            jpeg_quality: JPEG compression quality (1-100).
            max_dimension: Maximum width/height; larger images are scaled.
        """
        self.jpeg_quality = jpeg_quality
        self.max_dimension = max_dimension

        try:
            from PIL import Image
            self._pil_image = Image
            self._pil_available = True
        except ImportError:
            self._pil_image = None
            self._pil_available = False

    def is_available(self) -> bool:
        """Check if scrot is installed."""
        try:
            result = subprocess.run(
                ['scrot', '--version'],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _optimize_image(self, png_data: bytes) -> Tuple[bytes, str, int, int]:
        """Optimize PNG screenshot to JPEG.

        Args:
            png_data: Raw PNG data from scrot.

        Returns:
            Tuple of (image_data, media_type, width, height).
        """
        if not self._pil_available:
            raise ScreenshotError(
                "Pillow library not installed. Install with: pip install Pillow",
                backend="scrot"
            )

        # Load PNG
        img = self._pil_image.open(BytesIO(png_data))
        width, height = img.size

        # Convert to RGB if necessary (PNG might have alpha)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # Resize if larger than max dimension
        if width > self.max_dimension or height > self.max_dimension:
            ratio = min(self.max_dimension / width, self.max_dimension / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            img = img.resize((new_width, new_height), self._pil_image.Resampling.LANCZOS)
            width, height = new_width, new_height

        # Convert to JPEG
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=self.jpeg_quality, optimize=True)

        return buffer.getvalue(), 'image/jpeg', width, height

    def capture_screen(self) -> Screenshot:
        """Capture the entire screen using scrot.

        Returns:
            Screenshot object with JPEG image data.

        Raises:
            ScreenshotError: If capture fails.
        """
        try:
            # Capture to stdout as PNG
            result = subprocess.run(
                ['scrot', '-o', '-', '-F', 'png'],
                capture_output=True,
                timeout=10,
            )

            if result.returncode != 0:
                raise ScreenshotError(
                    f"scrot failed: {result.stderr.decode()}",
                    backend="scrot"
                )

            # Optimize to JPEG
            image_data, media_type, width, height = self._optimize_image(result.stdout)

            return Screenshot(
                image_data=image_data,
                media_type=media_type,
                width=width,
                height=height,
                timestamp=time.time(),
            )

        except subprocess.TimeoutExpired:
            raise ScreenshotError("scrot command timed out", backend="scrot")
        except FileNotFoundError:
            raise ScreenshotError(
                "scrot not found. Install with: sudo apt install scrot",
                backend="scrot"
            )
        except Exception as e:
            if isinstance(e, ScreenshotError):
                raise
            raise ScreenshotError(f"Failed to capture screen: {e}", backend="scrot") from e

    def capture_window(self, window_id: str) -> Screenshot:
        """Capture a specific window using scrot.

        Note: scrot's window capture activates the window first.

        Args:
            window_id: X11 window ID.

        Returns:
            Screenshot object with JPEG image data.

        Raises:
            ScreenshotError: If capture fails.
        """
        try:
            # First activate the window
            subprocess.run(
                ['xdotool', 'windowactivate', '--sync', window_id],
                capture_output=True,
                timeout=5,
            )

            # Brief pause for window to come to front
            time.sleep(0.2)

            # Capture focused window
            result = subprocess.run(
                ['scrot', '-u', '-o', '-', '-F', 'png'],
                capture_output=True,
                timeout=10,
            )

            if result.returncode != 0:
                raise ScreenshotError(
                    f"scrot failed: {result.stderr.decode()}",
                    backend="scrot"
                )

            # Optimize to JPEG
            image_data, media_type, width, height = self._optimize_image(result.stdout)

            return Screenshot(
                image_data=image_data,
                media_type=media_type,
                width=width,
                height=height,
                timestamp=time.time(),
            )

        except subprocess.TimeoutExpired:
            raise ScreenshotError("scrot command timed out", backend="scrot")
        except Exception as e:
            if isinstance(e, ScreenshotError):
                raise
            raise ScreenshotError(f"Failed to capture window: {e}", backend="scrot") from e


def create_screenshot_backend(config: Optional[dict] = None) -> ScreenshotBackend:
    """Factory function to create appropriate screenshot backend.

    Args:
        config: Optional configuration dictionary with 'intervention' section.

    Returns:
        An appropriate ScreenshotBackend instance.

    Raises:
        ScreenshotError: If no compatible backend is available.
    """
    config = config or {}
    intervention_config = config.get('intervention', {})
    backend_type = intervention_config.get('screenshot_backend', 'auto')
    jpeg_quality = intervention_config.get('jpeg_quality', 85)
    max_dimension = intervention_config.get('max_screenshot_dimension', 1920)

    if backend_type == 'scrot':
        backend = ScrotBackend(jpeg_quality=jpeg_quality, max_dimension=max_dimension)
        if not backend.is_available():
            raise ScreenshotError(
                "scrot backend requested but scrot is not installed",
                backend="scrot"
            )
        logger.info("Using scrot screenshot backend")
        return backend

    elif backend_type == 'mss':
        backend = MSSBackend(jpeg_quality=jpeg_quality, max_dimension=max_dimension)
        if not backend.is_available():
            raise ScreenshotError(
                "mss backend requested but mss/Pillow is not installed",
                backend="mss"
            )
        logger.info("Using mss screenshot backend")
        return backend

    else:  # auto
        # Prefer mss for portability, fall back to scrot
        mss_backend = MSSBackend(jpeg_quality=jpeg_quality, max_dimension=max_dimension)
        if mss_backend.is_available():
            logger.info("Auto-selected mss screenshot backend")
            return mss_backend

        scrot_backend = ScrotBackend(jpeg_quality=jpeg_quality, max_dimension=max_dimension)
        if scrot_backend.is_available():
            logger.info("Auto-selected scrot screenshot backend (mss unavailable)")
            return scrot_backend

        raise ScreenshotError(
            "No screenshot backend available. Install mss and Pillow: pip install mss Pillow",
            backend="auto"
        )
