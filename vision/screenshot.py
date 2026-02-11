from PIL import Image
import mss


def capture_roi(roi: dict) -> Image.Image:
    if roi["width"] <= 1 or roi["height"] <= 1:
        raise ValueError("ROI size is too small. Recalibrate and drag a larger area.")
    with mss.mss() as sct:
        monitor = {
            "left": roi["x"],
            "top": roi["y"],
            "width": roi["width"],
            "height": roi["height"],
        }
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
