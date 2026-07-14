"""
Tests for the caption error-type classifier (Load-Bearing Artifact #4).

Tests:
1. Heuristic mode (no trained weights): known recognition errors and edition errors
2. Trained mode: macro-F1 on synthetic held-out set must be > 0.65
3. Feature extraction: correct vector shape and range
4. Persistence: save/load round-trip
5. classify_error convenience function
"""
from __future__ import annotations
import numpy as np
import pytest
from sklearn.model_selection import train_test_split
from src.classifier import ErrorTypeClassifier, classify_error, _build_synthetic_training_data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def trained_clf():
    """Train a classifier on synthetic data once per module."""
    data = _build_synthetic_training_data(n_per_class=200)
    train_data, _ = train_test_split(data, test_size=0.2, random_state=42)
    clf = ErrorTypeClassifier()
    clf.fit(train_data)
    return clf


@pytest.fixture(scope="module")
def test_data():
    """Hold-out test data, consistent with trained_clf fixture split."""
    data = _build_synthetic_training_data(n_per_class=200)
    _, test = train_test_split(data, test_size=0.2, random_state=42)
    return test


# ---------------------------------------------------------------------------
# Feature extraction tests
# ---------------------------------------------------------------------------

class TestFeatureExtraction:
    def test_feature_vector_shape(self):
        clf = ErrorTypeClassifier()
        feat = clf.extract_features("there", "their", 0.4, "substitute")
        assert feat.shape == (7,)

    def test_feature_range_all_valid(self):
        clf = ErrorTypeClassifier()
        feat = clf.extract_features("begin", "start", 0.9, "substitute")
        # confidence-derived features should be in [0, 1]
        assert 0.0 <= feat[3] <= 1.0  # confidence
        assert 0.0 <= feat[4] <= 1.0  # phonetic similarity
        assert 0.0 <= feat[4] <= 1.0  # semantic similarity

    def test_equal_type_all_zeros_except_confidence(self):
        clf = ErrorTypeClassifier()
        feat = clf.extract_features("the", "the", 0.98, "equal")
        assert feat[0] == 0.0  # is_sub = 0
        assert feat[1] == 0.0  # is_del = 0
        assert feat[2] == 0.0  # is_ins = 0

    def test_delete_type_flags(self):
        clf = ErrorTypeClassifier()
        feat = clf.extract_features("word", "", 0.5, "delete")
        assert feat[1] == 1.0  # is_del = 1
        assert feat[0] == 0.0  # is_sub = 0

    def test_insert_type_flags(self):
        clf = ErrorTypeClassifier()
        feat = clf.extract_features("", "extra", 0.3, "insert")
        assert feat[2] == 1.0  # is_ins = 1


# ---------------------------------------------------------------------------
# Heuristic mode (no trained weights)
# ---------------------------------------------------------------------------

class TestHeuristicMode:
    def test_equal_is_always_correct(self):
        clf = ErrorTypeClassifier()  # no model loaded
        result = clf.classify_error("the", "the", 0.99, "equal")
        assert result == "correct"

    def test_phonetically_similar_low_confidence_is_recognition(self):
        clf = ErrorTypeClassifier()
        # "there" → "their": phonetically similar, low confidence
        result = clf.classify_error("there", "their", 0.3, "substitute")
        assert result == "recognition_error"

    def test_high_confidence_deletion_is_edition(self):
        clf = ErrorTypeClassifier()
        result = clf.classify_error("um", "", 0.9, "delete")
        assert result == "edition_error"


# ---------------------------------------------------------------------------
# Trained classifier
# ---------------------------------------------------------------------------

class TestTrainedClassifier:
    def test_macro_f1_above_threshold(self, trained_clf, test_data):
        """Load-bearing requirement: macro-F1 > 0.65 on held-out set."""
        metrics = trained_clf.evaluate(test_data)
        assert metrics["macro_f1"] > 0.65, (
            f"Macro-F1 {metrics['macro_f1']:.3f} below minimum 0.65. "
            f"Report:\n{metrics['report']}"
        )

    def test_known_recognition_error_classified_correctly(self, trained_clf):
        """Known recognition pair: 'peace' → 'piece', low confidence."""
        result = trained_clf.classify_error("peace", "piece", 0.25, "substitute")
        assert result == "recognition_error"

    def test_known_edition_error_classified_correctly(self, trained_clf):
        """Known edition pair: 'big' → 'large', high confidence."""
        result = trained_clf.classify_error("big", "large", 0.92, "substitute")
        assert result == "edition_error"

    def test_correct_classified_correctly(self, trained_clf):
        """Equal chunks are always 'correct' regardless of model."""
        result = trained_clf.classify_error("the", "the", 0.98, "equal")
        assert result == "correct"

    def test_output_is_valid_label(self, trained_clf):
        valid_labels = {"recognition_error", "edition_error", "correct"}
        for edit_type in ("substitute", "delete", "insert", "equal"):
            result = trained_clf.classify_error("word", "word", 0.7, edit_type)
            assert result in valid_labels


# ---------------------------------------------------------------------------
# Persistence: save/load round-trip
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_and_load(self, trained_clf, tmp_path):
        save_path = tmp_path / "classifier.pkl"
        trained_clf.save(save_path)
        assert save_path.exists()

        # Load and verify prediction is same
        loaded = ErrorTypeClassifier.load(save_path)
        r1 = trained_clf.classify_error("peace", "piece", 0.25, "substitute")
        r2 = loaded.classify_error("peace", "piece", 0.25, "substitute")
        assert r1 == r2

    def test_load_nonexistent_falls_back_to_heuristic(self, tmp_path):
        missing = tmp_path / "no_file.pkl"
        clf = ErrorTypeClassifier.load(missing)
        # Should not raise; falls back to heuristic
        result = clf.classify_error("there", "their", 0.3, "substitute")
        assert result in {"recognition_error", "edition_error", "correct"}


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

class TestConvenienceFunction:
    def test_classify_error_returns_valid_label(self):
        """The module-level function should return a valid label."""
        result = classify_error("the", "the", 0.99, "equal")
        assert result == "correct"

    def test_classify_error_caches_model(self):
        """Calling classify_error twice should use the cached model."""
        import src.classifier as clf_module
        result1 = classify_error("peace", "piece", 0.25, "substitute")
        model_after_first = clf_module._MODEL
        result2 = classify_error("peace", "piece", 0.25, "substitute")
        model_after_second = clf_module._MODEL
        # Same model object used
        assert model_after_first is model_after_second
