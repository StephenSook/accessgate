# Caption Error-Type Classifier: Label Schema

## Two-class schema (plus null class)

This schema governs annotation of caption error chunks produced by
`jiwer.process_words(reference, hypothesis)`.

### `recognition_error`

A word-level error where the ASR system heard the audio incorrectly.
Signals:
- Phonetically similar to the reference word (soundex overlap, Jaro-Winkler > 0.75)
- Low ASR confidence (faster-whisper word probability < 0.6)
- Meaning NOT preserved (semantic similarity <= 0.85)

Examples: "there" -> "their", "peace" -> "piece", "write" -> "right"

### `edition_error`

A word-level error where a human captioner made a deliberate choice:
a meaning-preserving paraphrase, synonym, or deliberate omission.
Signals:
- High ASR confidence (> 0.75) — the word was recognized but changed editorially
- Semantic similarity > 0.85 (meaning preserved)
- OR: deliberate omission of a filler word (um, uh, you know)

Examples: "automobile" -> "car", "begin" -> "start", "I think" -> omitted

### `correct`

No error: the reference and hypothesis words are identical (jiwer "equal" chunk).

## Annotation guidelines

1. Read the reference word and hypothesis word in context (surrounding sentence).
2. Listen to (or read) the ASR confidence score: < 0.6 = likely recognition error.
3. Check phonetic similarity: if the words sound alike, lean recognition.
4. Check semantic similarity: if the words mean the same thing in context, lean edition.
5. When in doubt, annotate as "recognition_error" (conservative; this protects against
   auto-failing captions due to editorial choices, per the Koenecke et al. bias rule).

## Double-annotation subset

For inter-annotator agreement: annotate 100 examples independently, then compute
Cohen's kappa. Target kappa >= 0.6 (substantial agreement).

## Data sources

- LibriSpeech test-clean (CC BY 4.0) — read speech, 16kHz, clean conditions
- Common Voice CC0 — crowd-sourced, diverse speakers
- AMI Meeting Corpus CC BY 4.0 — spontaneous meeting speech
- VoxPopuli CC0 — European Parliament speech

All sources are publicly licensed and may be redistributed.
