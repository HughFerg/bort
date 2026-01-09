# Solutions for Current Issues

## Issues Identified:

1. **Over-assignment**: Characters like Moe and Smithers detected in 34% of frames (too many false positives)
2. **Intro/Credits**: 663 frames (11%) are intro/credit sequences
3. **Generic captions**: "The simpsons family" appears 215 times

## Option A: Balanced Approach (RECOMMENDED)

**Fix Character Detection:**
- Raise `min_score` from 0.24 → **0.27**
- Lower `score_gap` from 0.05 → **0.03**
- Lower `max_chars` from 3 → **2**

**Expected Results:**
- Reduce false positives significantly
- Still detect characters in ~85-90% of frames (vs 92% now)
- More accurate character tags

**Filter Intro/Credits:**
- Skip frames 0-90 seconds (intro)
- Skip last 60 seconds (credits)
- **Saves 663 frames = 11% reduction**

**Total Impact:**
- From 5,915 → ~5,250 frames
- Much more accurate character detection
- Cleaner, more useful database

## Option B: Conservative (Highest Accuracy)

**Character Detection:**
- `min_score` = 0.30 (original strict setting)
- `score_gap` = 0.02
- `max_chars` = 1 (only most confident character)

**Expected Results:**
- Very few false positives
- Only ~60-70% detection rate
- But what IS detected is highly accurate

**Keep all frames** (no intro/credits filtering)

## Option C: Keep Current (High Coverage)

**Don't change anything**
- Accept some false positives for 92% coverage
- Users can mentally filter out wrong tags
- All frames remain indexed

## Recommendation: Option A

**Why:**
- Balances accuracy vs coverage
- Removes repetitive intro/credits content
- Fixes the Moe/Smithers over-detection issue
- Results in cleaner, more useful search

**Implementation:**
```bash
# 1. Update index.py thresholds
# 2. Add filtering for timestamps 0-90s and last 60s
# 3. Re-index (takes ~2-3 hours)
```

**Would reduce indexing from:**
- 5,915 frames → ~5,250 frames (-11%)
- 92% character detection → ~85-88% detection
- But much fewer false positives!
