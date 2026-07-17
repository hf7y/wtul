#!/bin/bash
# Rip an audio CD to MP3 via abcde. Invoked by udev/systemd when a disc is
# inserted into an optical drive (see etc/udev/99-cd-autorip.rules).
#
# abcde is configured (~/.abcde.conf, LOWDISK=y) to encode one track at a
# time and delete its wav as soon as the mp3 is written. That means if the
# process is interrupted — disc yanked, power loss, Ctrl+C on a manual run —
# whatever tracks finished encoding before the interrupt are left behind as
# complete, playable mp3 files; there's no half-written track and nothing
# already ripped is lost. The disc is only ejected on a clean finish
# (EJECTCD=y in abcde.conf), so a partial/failed rip leaves the disc in the
# drive for you to retry.
#
# Safeguards below exist for a failing/dying drive: one that spins forever
# retrying bad sectors, or that spews endless read-error lines. Without
# these, a single bad disc can hang indefinitely and grow one log file
# without bound.

set -uo pipefail

DEVNAME="${1:?device kernel name required, e.g. sr0}"
DEV="/dev/${DEVNAME}"
RIPDIR="${HOME}/Music/ripped"
LOGDIR="${RIPDIR}/.logs"
mkdir -p "$LOGDIR"
LOGFILE="${LOGDIR}/$(date -Is | tr : -)-${DEVNAME}.log"
LOCKFILE="/tmp/cd-autorip-${DEVNAME}.lock"

MAX_RUNTIME="${MAX_RUNTIME:-2700}"       # 45 min wall-clock cap for one disc
MAX_LOG_BYTES="${MAX_LOG_BYTES:-5000000}" # 5 MB cap per run's log
MIN_FREE_KB="${MIN_FREE_KB:-524288}"      # refuse to start with <512MB free
KEEP_LOG_DAYS="${KEEP_LOG_DAYS:-14}"

exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "$(date -Is): rip already in progress for ${DEV}, skipping" >> "$LOGFILE"
    exit 0
fi

# Prune old run logs so a string of bad discs over time doesn't accumulate
# forever, and remove any abcde temp dirs (~/Music/ripped/abcde.<discid>)
# left behind by a run that had to be SIGKILLed and never got to clean up
# after itself.
find "$LOGDIR" -maxdepth 1 -name '*.log' -mtime "+${KEEP_LOG_DAYS}" -delete
find "$RIPDIR" -maxdepth 1 -type d -name 'abcde.*' -mmin +360 -exec rm -rf {} + 2>/dev/null

echo "$(date -Is): starting rip of ${DEV}" >> "$LOGFILE"

FREE_KB=$(df -Pk "$RIPDIR" | awk 'NR==2 {print $4}')
if [ "${FREE_KB:-0}" -lt "$MIN_FREE_KB" ]; then
    echo "$(date -Is): only ${FREE_KB}KB free at ${RIPDIR}, refusing to start (need ${MIN_FREE_KB}KB) - disc left in drive" >> "$LOGFILE"
    exit 1
fi

# timeout bounds total run time (a truly bad drive can otherwise retry the
# same sector forever); head -c bounds how much a chatty failure can write
# to this log file, regardless of how long it runs. PIPESTATUS[0] recovers
# abcde/timeout's real exit code even though it's piped through head.
timeout --signal=TERM --kill-after=30s "$MAX_RUNTIME" abcde -d "$DEV" 2>&1 \
    | head -c "$MAX_LOG_BYTES" >> "$LOGFILE"
RC=${PIPESTATUS[0]}

LOG_BYTES=$(stat -c%s "$LOGFILE" 2>/dev/null || echo 0)

# abcde can print "[ERROR] ... failed to run" for a track (e.g. a real disc
# read error from cdparanoia) and still exit 0 itself - its process exit
# code alone is not trustworthy. Treat any [ERROR] line as a failed rip
# regardless of what abcde returned.
if [ "$RC" -eq 0 ] && grep -q '^\[ERROR\]' "$LOGFILE"; then
    echo "$(date -Is): rip of ${DEV} logged an [ERROR] (see above) despite exiting 0 - treating as failed" >> "$LOGFILE"
    RC=1
fi

if [ "$LOG_BYTES" -ge "$MAX_LOG_BYTES" ]; then
    echo "$(date -Is): rip of ${DEV} log hit the ${MAX_LOG_BYTES}-byte cap and was truncated - likely a bad disc/drive spamming errors; disc left in drive" >> "$LOGFILE"
    [ "$RC" -eq 0 ] && RC=1
elif [ "$RC" -eq 124 ]; then
    echo "$(date -Is): rip of ${DEV} TIMED OUT after ${MAX_RUNTIME}s - possible bad drive/disc, killed; disc left in drive" >> "$LOGFILE"
elif [ "$RC" -eq 0 ]; then
    echo "$(date -Is): rip of ${DEV} completed successfully" >> "$LOGFILE"
else
    echo "$(date -Is): rip of ${DEV} exited with code ${RC} (interrupted or failed) - any tracks finished before the interrupt are kept in ${RIPDIR}, disc left in drive for retry" >> "$LOGFILE"
fi

exit "$RC"
