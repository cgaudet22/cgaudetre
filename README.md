# Pipeline Specification

## TTS

When a segment fails TTS generation, the system MUST generate fallback silence with a deterministic duration per failed segment.

### Fallback silence duration derivation

1. **Preferred method (required first attempt):**
   - Estimate the segment duration from the segment's word count and the target narration rate for the selected voice model.
   - Use a deterministic calculation so repeated runs produce the same fallback duration for identical input.
   - Example formula:
     - `target_seconds = word_count / words_per_second_for_selected_voice`
   - Clamp to configured minimum/maximum segment duration bounds if defined by pipeline settings.

2. **Alternate method (required second attempt before silence):**
   - Attempt backup narration through a configured secondary TTS provider.
   - If backup narration succeeds, use that generated narration audio and skip silence fallback for that segment.
   - If backup narration fails, use silence with duration computed from the preferred method above.

### Segment manifest requirements

Before concatenation, the pipeline MUST write a segment manifest file with one record per segment, including at least:

- `segment_index`
- `text_length` (character count)
- `target_seconds` (planned segment duration)
- `actual_audio_seconds` (measured duration of generated audio, backup audio, or silence)

The manifest MAY be JSON or CSV, but it MUST be deterministic and reproducible for the same input ordering.

### Pre-mux validation requirements

Before final muxing, the pipeline MUST validate total timeline length using the segment manifest:

1. Sum all `actual_audio_seconds` from concatenated segment outputs.
2. Compare this sum against the expected concatenated output duration (within configured tolerance).
3. Fail fast (and log a validation error) if the difference exceeds tolerance.
4. Proceed to final muxing only when validation passes.

These checks ensure predictable sync behavior even when one or more segments rely on fallback silence.
