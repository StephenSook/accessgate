---
name: conformance
description: Use when authoring, editing, or reviewing accessibility conformance rules for captions and audio description. Encodes the WCAG 2.2, FCC 47 CFR 79.1, DCMP Captioning Key, DCMP Description Key, and Netflix rule tables plus the required citation format. Invoke this skill whenever a task touches rule logic, the NER scorer, the audio-description structure validator, or the rule registry.
---

# Conformance rule authoring for AccessGate

When you author or edit any rule, emit these fields for it: a rule ID, the source citation (standard, section, and a verbatim short quote where confirmed), the check type (automated, automated-with-band, or human-judgment-flag), the required inputs (caption file, AD file, VAD regions, reference transcript, video metadata), a one-sentence pass/fail rule, and a SARIF level (error, warning, or note).

Citations are retrieved from the parsed standard text via the RAG layer. Do not hardcode a citation from memory.

## Locked claim language

The product is a "conformance pre-check: automatable checks plus human-judgment flags." Never write "conformance checker" or "certifier."

## FCC 47 CFR 79.1(j)(2) caption quality (four factors)

- Accuracy: captions match the spoken words in order, correct spelling and homophones, punctuation, capitalization, tense, and number formatting, and include non-speech information. Metric: (total words minus errors) divided by total words. Score with the NER-style method (NER = (N minus E minus R) divided by N), reference-relative, confidence-banded, and never auto-fail on ASR evidence alone.
- Synchronicity: captions begin when speech begins and end approximately when speech ends, displayed at a readable speed.
- Completeness: captions run from the beginning to the end of the program.
- Placement: captions do not block faces, essential visuals, or on-screen text, and do not overlap or run off-screen.

## WCAG 2.2

- SC 1.2.2 Captions (Prerecorded), Level A: captions are provided for all prerecorded audio content in synchronized media.
- SC 1.2.5 Audio Description (Prerecorded), Level AA: audio description is provided for all prerecorded video content in synchronized media. Presence and timing are automatable; semantic sufficiency is a human-judgment flag.

## DCMP Captioning Key (codeable numbers)

- Reading speed: lower-level educational not to exceed 130 wpm, middle-level 140 wpm, upper-level 160 wpm. Adult near-verbatim, but no caption stays on screen under 2 seconds or exceeds 225 wpm.
- Lines: 32 characters or fewer per line, 1 to 2 lines per caption.
- Sound effects: identify the source in brackets, placed close to the sound source. Never use past tense for sounds; captions are synchronized with the sound and are therefore present tense.

## DCMP Description Key (codeable rules)

- Present tense, active voice. Third-person narrative. Complete sentences where possible.
- Do not try to fill every pause. Do not describe over audio essential to comprehension.
- Describe objectively without interpretation, censorship, or comment (objectivity is a human-judgment flag).
- Match vocabulary to the program and wait until technical vocabulary has been introduced before using it (encode as an avoid-premature-jargon rule).
- Fit each description within its dialogue-free gap: measured words-per-minute against the gap duration.

## Netflix English delivery profile

- Reading speed 20 characters per second for adult programs, 17 for children's.
- 42 characters per line maximum, 2 lines maximum per event.
- Minimum duration five-sixths of a second, maximum 7 seconds per event, with a 2-frame minimum gap between events.

## Rule ID convention

Family prefix plus a number: FCC-ACC, FCC-SYN, FCC-CMP, FCC-PLC, WCAG-122, WCAG-125, DCMP-CAP, DCMP-DESC, NFLX-CPS, NFLX-LEN, NFLX-DUR.
