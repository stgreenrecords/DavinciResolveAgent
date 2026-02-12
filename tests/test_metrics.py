from vision.metrics import ConvergenceDetector, MetricsNormalizer, SimilarityMetrics


def test_metrics_normalizer_full_match():
    score = MetricsNormalizer.normalize(ssim=1.0, histogram=0.0, delta_e=0.0)
    assert score == 1.0


def test_convergence_detector_triggers():
    detector = ConvergenceDetector(window_size=3, threshold=0.02)
    metrics = [
        SimilarityMetrics(ssim=0.9, histogram=0.1, delta_e=1.0, overall=0.5),
        SimilarityMetrics(ssim=0.9, histogram=0.1, delta_e=1.0, overall=0.51),
        SimilarityMetrics(ssim=0.9, histogram=0.1, delta_e=1.0, overall=0.505),
    ]
    assert detector.add(metrics[0]) is False
    assert detector.add(metrics[1]) is False
    assert detector.add(metrics[2]) is True
