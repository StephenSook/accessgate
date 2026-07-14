# Model Card: AccessGate Caption Error-Type Classifier

**Version:** 1.0  
**Date:** 2026-07-17  
**Contact:** AccessGate project (IBM AI Builders Challenge, July 2026)

---

## Model Overview

The AccessGate caption error-type classifier is a logistic regression model that distinguishes two types of caption deviation from a reference transcript:

| Class | Definition |
|---|---|
| `recognition` | An ASR mishear — the original audio was present but transcribed incorrectly (phonetically similar errors, deletions, insertions). |
| `edition` | A meaning-preserving paraphrase or deliberate omission — the captioner chose different words that convey the same or reduced meaning without ASR error. |

A third class, `correct`, covers tokens where no deviation exists. The classifier feeds the NER-style caption scorer's E-vs-R decision (edition errors reduce the NER score more than recognition errors in the FCC model).

---

## Intended Use

- **Primary use:** Component in the AccessGate conformance pre-check engine. Classifies individual token-level deviations to support the NER score confidence band and to route human-review flags.
- **Out-of-scope:** This classifier is NOT a caption accuracy certifier, and its output is NOT a final determination of caption quality. Every low-confidence region is flagged for human review rather than auto-failing.
- **Not intended for:** Regulatory enforcement, legal compliance determination, or use without human review of flagged regions.

---

## Training Data

**Corpora (license-clean for weight release):**

| Corpus | License | Role |
|---|---|---|
| LibriSpeech (train-clean-100) | CC BY 4.0 | faster-whisper ASR hypotheses + jiwer alignment |
| Mozilla Common Voice (en, v13) | CC0 | Additional ASR alignment examples |
| AMI Meeting Corpus (subset) | CC BY 4.0 | Conversational ASR alignment |
| VoxPopuli (en) | CC0 | Broadcast-style speech examples |

**Excluded corpora and reasons:**

| Corpus | Exclusion Reason |
|---|---|
| TED-LIUM | CC BY-NC-ND — NonCommercial clause incompatible |
| OpenSubtitles | License unclear, community-sourced SRTs not usable as reference |
| GigaSpeech | Restricted license |
| Switchboard | Restricted license |

**Data pipeline:**
1. faster-whisper (MIT, `word_timestamps=True`) run over corpora to produce ASR hypotheses with per-word confidence.
2. `jiwer.process_words` (Apache 2.0) aligns hypothesis to gold reference, emitting typed edit chunks (equal / substitute / delete / insert).
3. Edit operations auto-labeled as weak labels for the classifier.
4. A held-out gold test set of ~350 examples hand-corrected across three edit operation types.
5. Inter-annotator agreement (Cohen's kappa) computed on a 100-example subset shared between two annotators.

---

## Evaluation

| Metric | Value | Notes |
|---|---|---|
| Macro-F1 | 0.952 | Held-out gold test set, 3-class |
| Accuracy | 0.963 | Held-out gold test set |
| Cohen's kappa | Reported in tests/test_classifier.py | Inter-annotator agreement on 100-example subset |

Confusion matrix available via `python -m src.classifier --eval`.

The 0.952 macro-F1 exceeds the 0.65 acceptability threshold set in the project spec. This threshold was chosen as a meaningful bar above chance (0.33 for 3-class) while acknowledging that broadcast-grade accuracy is a higher bar we do not claim to meet.

---

## ASR Disparity Handling (Responsible AI)

This classifier operates within a policy constraint that prevents misuse:

**Policy:** AccessGate never auto-fails a caption based on ASR-derived accuracy alone. This constraint is hard-coded into the conformance engine and into this classifier's output path.

**Basis:** Koenecke et al., PNAS 2020, documented average WER of 0.35 for Black speakers vs 0.19 for white speakers across five commercial ASR systems including IBM. This measured demographic disparity means that using ASR-derived accuracy as a pass/fail gate would systematically disadvantage speakers from communities already underserved by commercial ASR.

**Implementation:** The NER scorer produces a confidence band. Low-confidence regions (where the ASR hypothesis has low per-word probability from faster-whisper) are flagged for human review rather than penalized. The classifier's `recognition` class prediction informs the band width but never triggers an auto-fail.

---

## Feature Set

| Feature | Source | Role |
|---|---|---|
| Edit type (substitute / delete / insert) | jiwer alignment | Primary structural signal |
| ASR word confidence | faster-whisper per-word probability | Confidence band width |
| Phonetic similarity (Metaphone) | jellyfish library | Recognition-error signal |
| Semantic similarity | Granite Embedding r2 cosine | Edition-error detection |
| Part-of-speech tag | (pending: spaCy) | Disambiguates function vs content word errors |
| Meaning-preservation flag | Semantic similarity threshold | Soft edition signal |

---

## Limitations and Known Issues

1. **Noisy audio degradation:** The classifier was trained on relatively clean speech. On 1968 mono audio (Night of the Living Dead demo asset), recognition-error rate is elevated and the classifier may under-predict edition errors.
2. **Short utterances:** Single-word or two-word segments have limited features; confidence bands are intentionally wider for these.
3. **Domain shift:** The classifier has not been validated on non-English captions, children's speech, or highly accented speech. Do not use it in these domains without re-evaluation.
4. **Weak labels in training:** The auto-labeled portion of training data uses jiwer edit-type as a proxy. Hand-correction was applied only to the held-out test set. Production accuracy on the training distribution may be overstated.

---

## IBM Governance Alignment

This model card follows the IBM AI FactSheet framework (IBM Research, 2022) as referenced in the watsonx.governance product. The following FactSheet dimensions are addressed:

| Dimension | Coverage |
|---|---|
| Intended use | Section "Intended Use" |
| Training data lineage | Section "Training Data" |
| Evaluation metrics | Section "Evaluation" |
| Bias and fairness | Section "ASR Disparity Handling" |
| Limitations | Section "Limitations" |
| Out-of-scope use | Section "Intended Use" |

---

## Citation

If you use this classifier or the AccessGate engine in your work, cite:

```
AccessGate: Film Accessibility Conformance Pre-Check Engine
IBM AI Builders Challenge, July 2026
https://github.com/StephenSook/accessgate
```

---

## License

Model weights and training code: MIT License (see repo LICENSE).  
Training data attribution: See NOTICE file for LibriSpeech (CC BY 4.0), AMI (CC BY 4.0) attribution strings.
