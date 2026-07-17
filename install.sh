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

sudo install -m 755 bin/cd-autorip.sh /usr/local/bin/cd-autorip.sh
sudo install -m 755 bin/wtul-rip /usr/local/bin/wtul-rip
sudo install -m 644 etc/systemd/cd-autorip@.service /etc/systemd/system/cd-autorip@.service

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
    echo "$HOME/.abcde.conf already exists — left it alone. Compare against abcde.conf in this repo if rips aren't behaving as expected."
fi

# wtul-rip always calls abcde with -c ~/.abcde-noeject.conf so abcde never
# ejects on its own (it otherwise does so at the end of ANY run, including
# the metadata-only scrape - before a single track gets ripped). wtul-rip
# is the only thing that ejects, and only once every requested track is done.
install -m 644 noeject.abcde.conf "$HOME/.abcde-noeject.conf"

sudo systemctl daemon-reload

cat <<'EOF'

Installed. To rip discs:
  wtul-rip

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
