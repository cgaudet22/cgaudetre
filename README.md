# Video Assembly Guide

## Video assembly

When slides/stills are assembled with crossfades, each transition overlaps two adjacent stills. That overlap must be subtracted from the naive total:

- **Total duration** = `(N × still_duration) - ((N - 1) × fade_duration)`

Where:
- `N` = number of stills
- `still_duration` = on-screen duration per still before overlap accounting
- `fade_duration` = transition overlap duration

### Exact still duration for 180 images, 1s fades, and a 3600s target

Given:
- `N = 180`
- `fade_duration = 1`
- `target_total = 3600`

Solve:

`3600 = (180 × still_duration) - ((180 - 1) × 1)`

`3600 = 180 × still_duration - 179`

`180 × still_duration = 3779`

`still_duration = 3779 / 180 = 20.994444444444...`

Use either:
- exact fraction: `3779/180`
- decimal (practical): `20.994444444444445`

## FFmpeg construction options

### Option A: Use adjusted still duration so overlap math lands at 3600s

If your transition graph introduces `N - 1` overlaps of `fade_duration`, set:

```bash
N=180
FADE=1
TARGET=3600
STILL=$(python3 - <<'PY'
from fractions import Fraction
N=180
FADE=1
TARGET=3600
print(float(Fraction(TARGET + (N-1)*FADE, N)))
PY
)
echo "$STILL"   # 20.994444444444444
```

Then build your `xfade` offsets with `STILL-FADE` spacing so each new clip starts after the previous non-overlapped segment.

### Option B: Keep your current still duration and force final timeline length

If your workflow must keep a different per-still duration, apply a final trim:

```bash
ffmpeg -i assembled_with_transitions.mp4 \
  -vf "trim=duration=3600,setpts=PTS-STARTPTS" \
  -af "atrim=duration=3600,asetpts=PTS-STARTPTS" \
  -c:v libx264 -c:a aac final_3600s.mp4
```

This preserves a strict 3600s runtime regardless of accumulated transition math.

## Post-render duration validation (required)

Validate output duration with `ffprobe`:

```bash
ffprobe -v error -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 final_3600s.mp4
```

Expected result should be `3600` seconds (allowing tiny container rounding, e.g. `3599.999` to `3600.001` depending on timebase).
