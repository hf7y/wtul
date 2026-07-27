#!/bin/bash
# Installs the CD auto-rip system: the wtul-rip CLI, its rip script, and a
# default ~/.abcde.conf if you don't already have one.
# Run this yourself (needs sudo): bash install.sh
#
# Discs no longer auto-rip on insert (the old udev rule is removed below).
# wtul-rip is now what starts a rip - run it, and it watches the drive for
# you, scraping metadata and letting you set track priority before each rip.

set -euo pipefail
cd "$(dirname "$0")"

# abcde needs eyeD3 to write id3v2.4 mp3 tags; without it every rip fails
# before ever touching the disc.
if ! command -v eyeD3 >/dev/null; then
    sudo apt-get install -y eyed3
fi

# sg3-utils' sg_raw is what the Apple USB SuperDrive udev rule below uses to
# send its required wake-up command - installed unconditionally since it's
# small and harmless even if you never plug in a SuperDrive.
if ! command -v sg_raw >/dev/null; then
    sudo apt-get install -y sg3-utils
fi

# Apple USB SuperDrive: enumerates but stays inert (no tray, no media
# events) until it receives a specific SCSI wake-up command. Only needed if
# you ever use one instead of an internal/other USB drive, but installing
# the rule unconditionally is harmless - it only fires for that exact
# vendor/product ID.
sudo install -m 644 etc/udev/90-mac-superdrive.rules /etc/udev/rules.d/90-mac-superdrive.rules
sudo udevadm control --reload-rules

sudo install -m 755 bin/cd-autorip.sh /usr/local/bin/cd-autorip.sh
sudo install -m 644 etc/systemd/cd-autorip@.service /etc/systemd/system/cd-autorip@.service

# wtul-rip imports lib/spinitron.py etc via a path relative to its own
# location (bin/../lib) - installing just the script to /usr/local/bin
# breaks that (no lib/ next to /usr/local/bin), so deploy the whole
# bin+lib tree under one prefix and symlink the entry point onto PATH.
# wtul-rip resolves symlinks (os.path.realpath) before computing that
# relative path, so this keeps working through the symlink.
sudo install -d -m 755 /usr/local/lib/wtul-rip/bin /usr/local/lib/wtul-rip/lib
sudo install -m 755 bin/wtul-rip /usr/local/lib/wtul-rip/bin/wtul-rip
sudo install -m 644 lib/*.py /usr/local/lib/wtul-rip/lib/
sudo ln -sf /usr/local/lib/wtul-rip/bin/wtul-rip /usr/local/bin/wtul-rip

# Remove the old udev auto-trigger if it's still installed from an earlier
# run of this script - wtul-rip replaces it as the thing that starts a rip.
if [ -f /etc/udev/rules.d/99-cd-autorip.rules ]; then
    sudo rm -f /etc/udev/rules.d/99-cd-autorip.rules
    sudo udevadm control --reload-rules
    echo "removed the udev auto-trigger - inserting a disc no longer rips it automatically"
fi

install -d -m 755 "$HOME/Music/ripped"

if [ ! -f "$HOME/.abcde.conf" ]; then
    install -m 644 abcde.conf "$HOME/.abcde.conf"
    echo "installed $HOME/.abcde.conf"
else
    # "Left it alone" used to be the whole story, and it silently ate the
    # 2026-07-24 ripped->mixes migration: the repo's OUTPUTDIR moved, the
    # installed copy didn't, and rips would have landed in ~/Music/ripped
    # while wtul-rip looked in ~/Music/mixes/<date>. Never overwrite a
    # config someone may have hand-edited - but never stay quiet about a
    # drift that breaks every rip either.
    echo "$HOME/.abcde.conf already exists — left it alone."
    if ! diff -q "$HOME/.abcde.conf" abcde.conf >/dev/null; then
        echo
        echo "WARNING: it differs from this repo's abcde.conf:"
        diff -u "$HOME/.abcde.conf" abcde.conf | sed 's/^/    /' || true
        echo
        echo "    Run 'wtul-rip doctor' to see whether the difference actually"
        echo "    breaks a rip (it checks OUTPUTDIR/WAVOUTPUTDIR against the"
        echo "    directory wtul-rip reads back)."
    fi
fi

# wtul-rip always calls abcde with -c ~/.abcde-noeject.conf so abcde never
# ejects on its own (it otherwise does so at the end of ANY run, including
# the metadata-only scrape - before a single track gets ripped). wtul-rip
# is the only thing that ejects, and only once every requested track is done.
install -m 644 noeject.abcde.conf "$HOME/.abcde-noeject.conf"

sudo systemctl daemon-reload

cat <<'EOF'

Installed. Before a show, check the rig is actually ready (no disc needed):
  wtul-rip doctor          - full preflight; exits nonzero if a rip can't work
  wtul-rip doctor --no-net - same, skipping the metadata-service probes

To rip discs:
  wtul-rip

If the drive isn't /dev/sr0 (e.g. a second/external drive, or an Apple
USB SuperDrive showing up as sr1), pass its name:
  wtul-rip sr1
Run `udevadm info -a -n /dev/sr1 | grep KERNEL` (or just `ls /dev/sr*`) to
find out what the system named it.

It watches /dev/sr0 and, on each disc you insert, looks up its metadata,
shows you the tracklist, and starts ripping immediately in track order -
no prompt, no waiting. While it's ripping you can type (then Enter):
  5 2                 - reprioritize remaining tracks (rip 5, then 2, then the rest)
  artist=Real Name    - fix the artist
  album=Real Album    - fix the album
  3=Real Track Title  - fix track 3's title
Press 'h' any time (when idle between discs) for rip history, 's' for
status, 'q' to quit.

If it's interrupted (Ctrl+C, disc ejected, drive dies) mid-rip, whatever
tracks finished first are already valid mp3s in ~/Music/ripped - nothing
already ripped is lost, and the disc stays in the drive so you can re-run
wtul-rip to pick up the remaining tracks.
EOF
