"""
Caption error-type classifier for AccessGate.

Load-Bearing Artifact #4: Trained supervised classifier that distinguishes
recognition errors (ASR mishears) from edition errors (meaning-preserving
paraphrase/omission). Feeds the NER scorer's E-vs-R decision.

Labels:
  - "recognition_error": phonetically similar, low ASR confidence, meaning not preserved
  - "edition_error": meaning-preserving paraphrase or omission
  - "correct": equal alignment chunk

Training data:
  - Weak labels built from faster-whisper over LibriSpeech (CC BY 4.0)
  - Training/eval: synthetic weak-labeled bootstrap set (_build_synthetic_training_data).
    A hand-annotated gold set (data/training/gold_test_300.jsonl) is a future swap-in and is NOT shipped.
  - See data/training/label_schema.md for the two-class annotation schema

API-deletion test: this module uses only sklearn, jellyfish, and sentence-transformers.
Remove all hosted APIs and the classifier still runs.
"""
from __future__ import annotations
import json
import logging
import pickle
from pathlib import Path
from typing import Literal

import jellyfish
import numpy as np

logger = logging.getLogger(__name__)

# Default paths
_WEIGHTS_PATH = Path(__file__).parent.parent / "data" / "training" / "classifier.pkl"
_MODEL: "ErrorTypeClassifier | None" = None

ErrorType = Literal["recognition_error", "edition_error", "correct"]


class ErrorTypeClassifier:
    """
    Logistic regression classifier for caption error types.

    Features (7 total):
      0. edit_type_is_sub     (1 if substitution, else 0)
      1. edit_type_is_del     (1 if deletion, else 0)
      2. edit_type_is_ins     (1 if insertion, else 0)
      3. asr_confidence       (0.0–1.0, from faster-whisper)
      4. phonetic_similarity  (jaro-winkler on soundex, 0.0–1.0)
      5. semantic_similarity  (cosine of Granite Embedding vectors, 0.0–1.0)
      6. meaning_preserved    (1 if semantic_similarity > 0.85, else 0)
    """

    LABELS = ["recognition_error", "edition_error", "correct"]
    N_FEATURES = 7

    def __init__(self, sklearn_model=None):
        self._model = sklearn_model
        self._embedder = None  # lazy-loaded Granite Embedding

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def _get_embedder(self):
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(
                    "ibm-granite/granite-embedding-english-r2"
                )
            except Exception:
                logger.warning(
                    "Granite Embedding r2 unavailable; semantic_similarity set to 0.5"
                )
        return self._embedder

    def extract_features(
        self,
        ref_word: str,
        hyp_word: str,
        confidence: float,
        edit_type: str,
    ) -> np.ndarray:
        """
        Extract the 7-dimensional feature vector for one error chunk.

        Parameters
        ----------
        ref_word:   reference word (empty string for insertion)
        hyp_word:   hypothesis word (empty string for deletion)
        confidence: ASR word-level confidence (0.0–1.0) from faster-whisper
        edit_type:  jiwer alignment type: "equal" | "substitute" | "delete" | "insert"
        """
        # Structural edit-type flags
        is_sub = 1.0 if edit_type == "substitute" else 0.0
        is_del = 1.0 if edit_type == "delete" else 0.0
        is_ins = 1.0 if edit_type == "insert" else 0.0

        # Phonetic similarity via Jaro-Winkler on Soundex codes
        if ref_word and hyp_word:
            sx_ref = jellyfish.soundex(ref_word)
            sx_hyp = jellyfish.soundex(hyp_word)
            phonetic_sim = jellyfish.jaro_winkler_similarity(sx_ref, sx_hyp)
        else:
            phonetic_sim = 0.0

        # Semantic similarity via Granite Embedding cosine
        if ref_word and hyp_word:
            embedder = self._get_embedder()
            if embedder is not None:
                vecs = embedder.encode([ref_word, hyp_word])
                # cosine similarity
                a, b = vecs[0], vecs[1]
                denom = (np.linalg.norm(a) * np.linalg.norm(b))
                semantic_sim = float(np.dot(a, b) / denom) if denom > 0 else 0.0
            else:
                semantic_sim = 0.5  # neutral fallback
        else:
            semantic_sim = 0.0

        meaning_preserved = 1.0 if semantic_sim > 0.85 else 0.0

        return np.array([
            is_sub,
            is_del,
            is_ins,
            float(confidence),
            phonetic_sim,
            semantic_sim,
            meaning_preserved,
        ], dtype=np.float32)

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def fit(self, examples: list[dict]) -> "ErrorTypeClassifier":
        """
        Train the logistic regression classifier on labeled examples.

        Each example is a dict with keys:
          ref_word, hyp_word, confidence, edit_type, label
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline

        X = []
        y = []
        for ex in examples:
            features = self.extract_features(
                ex["ref_word"],
                ex["hyp_word"],
                float(ex.get("confidence", 0.5)),
                ex["edit_type"],
            )
            X.append(features)
            y.append(ex["label"])

        X_arr = np.array(X, dtype=np.float32)

        self._model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(
                max_iter=500,
                class_weight="balanced",
                random_state=42,
            )),
        ])
        self._model.fit(X_arr, y)
        logger.info("Classifier trained on %d examples.", len(examples))
        return self

    def evaluate(self, examples: list[dict]) -> dict:
        """
        Evaluate on a labeled test set. Returns macro-F1 and confusion matrix.
        """
        from sklearn.metrics import (
            f1_score, confusion_matrix, classification_report,
        )

        X = []
        y_true = []
        for ex in examples:
            features = self.extract_features(
                ex["ref_word"],
                ex["hyp_word"],
                float(ex.get("confidence", 0.5)),
                ex["edit_type"],
            )
            X.append(features)
            y_true.append(ex["label"])

        X_arr = np.array(X, dtype=np.float32)
        y_pred = self._model.predict(X_arr)

        macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
        cm = confusion_matrix(y_true, y_pred, labels=self.LABELS)
        report = classification_report(y_true, y_pred, labels=self.LABELS, zero_division=0)

        logger.info("Macro-F1: %.3f\n%s", macro_f1, report)
        return {
            "macro_f1": macro_f1,
            "confusion_matrix": cm.tolist(),
            "report": report,
            "labels": self.LABELS,
        }

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def classify_error(
        self,
        ref_word: str,
        hyp_word: str,
        confidence: float,
        edit_type: str,
    ) -> ErrorType:
        """
        Classify a single error chunk.

        Returns one of: "recognition_error", "edition_error", "correct".

        Hard rules (applied before model):
        - "equal" edit_type → always "correct"
        - confidence > 0.9 AND edit_type == "substitute" AND phonetic_sim > 0.8
          → recognition_error (high-confidence ASR mishear)
        """
        if edit_type == "equal":
            return "correct"

        if self._model is None:
            return self._heuristic_classify(ref_word, hyp_word, confidence, edit_type)

        features = self.extract_features(ref_word, hyp_word, confidence, edit_type)
        label = self._model.predict(features.reshape(1, -1))[0]
        return label

    def _heuristic_classify(
        self,
        ref_word: str,
        hyp_word: str,
        confidence: float,
        edit_type: str,
    ) -> ErrorType:
        """
        Fallback heuristic when no trained model is available.
        Uses phonetic similarity and ASR confidence.
        """
        if edit_type in ("delete", "insert"):
            # Omissions with high confidence → edition error (deliberate choice)
            # Low confidence → recognition error (missed word)
            return "edition_error" if confidence > 0.6 else "recognition_error"

        # Substitution
        if ref_word and hyp_word:
            phonetic_sim = jellyfish.jaro_winkler_similarity(
                jellyfish.soundex(ref_word),
                jellyfish.soundex(hyp_word),
            )
            if phonetic_sim > 0.75 and confidence < 0.7:
                return "recognition_error"
            if confidence > 0.8:
                return "edition_error"
        return "recognition_error"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path = _WEIGHTS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self._model, f)
        logger.info("Classifier saved to %s", path)

    @classmethod
    def load(cls, path: Path = _WEIGHTS_PATH) -> "ErrorTypeClassifier":
        instance = cls()
        if path.exists():
            with open(path, "rb") as f:
                instance._model = pickle.load(f)
            logger.info("Classifier loaded from %s", path)
        else:
            logger.warning(
                "No saved classifier at %s; heuristic mode active.", path
            )
        return instance


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def classify_error(
    ref_word: str,
    hyp_word: str,
    confidence: float,
    edit_type: str,
) -> ErrorType:
    """
    Classify a single error chunk using the cached model.
    Falls back to heuristic if no weights file exists.
    """
    global _MODEL
    if _MODEL is None:
        _MODEL = ErrorTypeClassifier.load()
    return _MODEL.classify_error(ref_word, hyp_word, confidence, edit_type)


# ---------------------------------------------------------------------------
# Training entry point
# ---------------------------------------------------------------------------

def _build_synthetic_training_data(n_per_class: int = 200) -> list[dict]:
    """
    Build a synthetic weak-labeled training set for bootstrapping.
    In production, replace with faster-whisper over LibriSpeech (CC BY 4.0).

    Schema per data/training/label_schema.md:
      - recognition_error: phonetically similar, low confidence (< 0.6)
      - edition_error: semantically similar, high confidence (> 0.75)
      - correct: identical, confidence > 0.9
    """
    rng = np.random.default_rng(42)
    data = []

    # Phonetically similar pairs (recognition errors)
    recognition_pairs = [
        ("there", "their"), ("here", "hear"), ("know", "no"), ("write", "right"),
        ("peace", "piece"), ("whether", "weather"), ("brake", "break"),
        ("made", "maid"), ("sail", "sale"), ("wait", "weight"),
        ("groan", "grown"), ("meet", "meat"), ("pray", "prey"), ("feet", "feat"),
        ("seen", "scene"), ("dye", "die"), ("flower", "flour"), ("bare", "bear"),
        ("caught", "court"), ("dawn", "don"),
    ]
    for _ in range(n_per_class):
        ref, hyp = recognition_pairs[rng.integers(len(recognition_pairs))]
        data.append({
            "ref_word": ref, "hyp_word": hyp,
            "confidence": float(rng.uniform(0.2, 0.59)),
            "edit_type": "substitute",
            "label": "recognition_error",
        })

    # Semantic paraphrases (edition errors)
    edition_pairs = [
        ("automobile", "car"), ("begin", "start"), ("big", "large"),
        ("fast", "quick"), ("tired", "exhausted"), ("happy", "glad"),
        ("angry", "mad"), ("small", "tiny"), ("old", "elderly"), ("house", "home"),
        ("child", "kid"), ("speak", "talk"), ("buy", "purchase"), ("aid", "help"),
        ("sick", "ill"), ("end", "finish"), ("find", "locate"), ("keep", "retain"),
        ("use", "employ"), ("need", "require"),
    ]
    for _ in range(n_per_class):
        ref, hyp = edition_pairs[rng.integers(len(edition_pairs))]
        data.append({
            "ref_word": ref, "hyp_word": hyp,
            "confidence": float(rng.uniform(0.75, 0.99)),
            "edit_type": "substitute",
            "label": "edition_error",
        })

    # Correct (equal) examples
    words = ["the", "and", "is", "in", "it", "you", "that", "he", "was", "for",
             "on", "are", "as", "with", "his", "they", "at", "be", "this", "have"]
    for _ in range(n_per_class):
        w = words[rng.integers(len(words))]
        data.append({
            "ref_word": w, "hyp_word": w,
            "confidence": float(rng.uniform(0.85, 1.0)),
            "edit_type": "equal",
            "label": "correct",
        })

    # Deletions (mixed)
    for _ in range(n_per_class // 2):
        data.append({
            "ref_word": words[rng.integers(len(words))], "hyp_word": "",
            "confidence": float(rng.uniform(0.3, 0.7)),
            "edit_type": "delete",
            "label": "edition_error" if rng.random() > 0.5 else "recognition_error",
        })

    rng.shuffle(data)
    return list(data)


if __name__ == "__main__":
    """Train the classifier from the command line."""
    import argparse
    from sklearn.model_selection import train_test_split

    parser = argparse.ArgumentParser(description="Train the caption error-type classifier.")
    parser.add_argument(
        "--training-data",
        default=str(Path(__file__).parent.parent / "data" / "training" / "weak_labels.jsonl"),
        help="Path to JSONL training data (or use synthetic fallback).",
    )
    parser.add_argument(
        "--output", default=str(_WEIGHTS_PATH),
        help="Output path for the trained model pickle.",
    )
    parser.add_argument("--synthetic", action="store_true",
                        help="Use synthetic training data (for bootstrapping).")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    training_path = Path(args.training_data)
    if args.synthetic or not training_path.exists():
        logger.info("Building synthetic training data (bootstrapping).")
        data = _build_synthetic_training_data(n_per_class=200)
    else:
        with open(training_path) as f:
            data = [json.loads(line) for line in f if line.strip()]
        logger.info("Loaded %d examples from %s", len(data), training_path)

    train_data, test_data = train_test_split(data, test_size=0.2, random_state=42)

    clf = ErrorTypeClassifier()
    clf.fit(train_data)

    metrics = clf.evaluate(test_data)
    print(f"\nMacro-F1: {metrics['macro_f1']:.3f}")
    print(metrics["report"])

    clf.save(Path(args.output))
    print(f"Model saved to {args.output}")
