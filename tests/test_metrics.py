from pathlib import Path

from PIL import Image

from vision.metrics import compute_metrics


def test_metrics_basic(tmp_path: Path):
    img = Image.new("RGB", (64, 64), color=(10, 20, 30))
    path = tmp_path / "ref.png"
    img.save(path)
    metrics = compute_metrics(path, img)
    assert metrics.overall > 0.9
