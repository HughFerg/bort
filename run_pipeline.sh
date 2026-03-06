#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Flanderize re-indexing pipeline
#
# Usage:
#   ./run_pipeline.sh                     # full run, all seasons
#   SEASON=s01 ./run_pipeline.sh          # staging: one season only
#   SEASON=s01 DB=data/staging.lance ./run_pipeline.sh
#
# Env overrides (or edit defaults below):
#   VIDEOS   - path to folder containing .mkv/.mp4 files
#   FRAMES   - where extracted frames are stored
#   DB       - LanceDB path
#   INTERVAL - seconds between frames (default: 1)
#   SEASON   - season filter, e.g. s01 (blank = all)
#   WORKERS  - thumbnail generation workers (default: 4)
#   PYTHON   - python binary to use (default: venv/bin/python)
# ─────────────────────────────────────────────────────────────────────────────

# ── Defaults ──────────────────────────────────────────────────────────────────
VIDEOS="${VIDEOS:-}"
FRAMES="${FRAMES:-data/frames}"
DB="${DB:-data/simpsons.lance}"
INTERVAL="${INTERVAL:-1}"
SEASON="${SEASON:-}"
WORKERS="${WORKERS:-4}"
PYTHON="${PYTHON:-venv/bin/python}"

# ── ANSI colours ──────────────────────────────────────────────────────────────
BOLD="\033[1m"
DIM="\033[2m"
RESET="\033[0m"
YELLOW="\033[33m"
GREEN="\033[32m"
RED="\033[31m"
CYAN="\033[36m"

# ── Helpers ───────────────────────────────────────────────────────────────────
hr() { printf "${DIM}%s${RESET}\n" "────────────────────────────────────────────────────────────────────────────"; }

stage() {
    local num="$1" total="$2" label="$3"
    echo ""
    hr
    printf "${BOLD}${YELLOW}  STAGE $num/$total  ${RESET}${BOLD}$label${RESET}\n"
    hr
}

ok() {
    local elapsed="$1"
    printf "${GREEN}  ✓ Done${RESET}${DIM} (${elapsed}s)${RESET}\n"
}

fail() {
    printf "${RED}  ✗ FAILED — aborting pipeline${RESET}\n"
    exit 1
}

elapsed_since() {
    echo $(( $(date +%s) - $1 ))
}

require() {
    if [ ! -f "$1" ]; then
        printf "${RED}Error: $1 not found. Are you running from the repo root?${RESET}\n"
        exit 1
    fi
}

# ── Validation ────────────────────────────────────────────────────────────────
require "$PYTHON"
require "index.py"
require "remove_black_frames.py"
require "generate_thumbnails.py"

if [ -z "$VIDEOS" ]; then
    printf "${RED}Error: VIDEOS path not set.\n"
    printf "Usage: VIDEOS=/path/to/videos ./run_pipeline.sh${RESET}\n"
    exit 1
fi

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
printf "${BOLD}${YELLOW}"
printf "  ███████ ██       █████  ███    ██ ██████  ███████ ██████  ██ ███████ ███████\n"
printf "  ██      ██      ██   ██ ████   ██ ██   ██ ██      ██   ██ ██    ███  ██\n"
printf "  █████   ██      ███████ ██ ██  ██ ██   ██ █████   ██████  ██   ███   █████\n"
printf "  ██      ██      ██   ██ ██  ██ ██ ██   ██ ██      ██   ██ ██  ███    ██\n"
printf "  ██      ███████ ██   ██ ██   ████ ██████  ███████ ██   ██ ██ ███████ ███████\n"
printf "${RESET}"
printf "${BOLD}  Re-indexing Pipeline${RESET}\n"
echo ""
printf "  ${DIM}Videos  ${RESET}${CYAN}$VIDEOS${RESET}\n"
printf "  ${DIM}Frames  ${RESET}${CYAN}$FRAMES${RESET}\n"
printf "  ${DIM}DB      ${RESET}${CYAN}$DB${RESET}\n"
printf "  ${DIM}Interval${RESET}${CYAN} ${INTERVAL}s${RESET}\n"
printf "  ${DIM}Season  ${RESET}${CYAN}${SEASON:-ALL}${RESET}\n"
echo ""

PIPELINE_START=$(date +%s)

# ── Stage 1: Extract & Index ──────────────────────────────────────────────────
stage 1 3 "Extract frames + build embeddings"

INDEX_ARGS=(
    "$PYTHON" index.py
    --videos "$VIDEOS"
    --frames "$FRAMES"
    --interval "$INTERVAL"
    --db "$DB"
)
[ -n "$SEASON" ] && INDEX_ARGS+=(--season "$SEASON")
[ -f "intro_credits.json" ] && INDEX_ARGS+=(--intro-cache intro_credits.json)

T=$(date +%s)
"${INDEX_ARGS[@]}" || fail
ok "$(elapsed_since $T)"

# ── Stage 2: Remove black frames ──────────────────────────────────────────────
stage 2 3 "Remove black / blank frames"

T=$(date +%s)
"$PYTHON" remove_black_frames.py \
    --db "$DB" \
    --delete || fail
ok "$(elapsed_since $T)"

# ── Stage 3: Generate thumbnails ──────────────────────────────────────────────
stage 3 3 "Generate WebP thumbnails"

T=$(date +%s)
"$PYTHON" generate_thumbnails.py \
    --frames-dir "$FRAMES" \
    --workers "$WORKERS" || fail
ok "$(elapsed_since $T)"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
hr
printf "${BOLD}${GREEN}  Pipeline complete!${RESET}"
printf "${DIM}  Total: $(elapsed_since $PIPELINE_START)s${RESET}\n"
hr
echo ""
printf "  Next: start the server and verify search quality\n"
printf "  ${DIM}uvicorn search:app --reload${RESET}\n"
echo ""
