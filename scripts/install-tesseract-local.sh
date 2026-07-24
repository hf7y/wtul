#!/bin/sh
# Install the tesseract-ocr CLI (+ English trained data) into the current
# user's home directory, without root/sudo. Needed for ROADMAP #7's OCR
# fallback on a machine where the tesseract-ocr apt package was never
# installed and no sudo password is available (the situation this
# machine was in as of 2026-07-24).
#
# `apt-get download` fetches a .deb without installing it (no root
# needed - it just needs network access to the configured apt sources).
# `dpkg-deb -x` extracts a .deb's file tree like any other archive.
# Nothing here touches the system package database or any path outside
# $INSTALL_DIR - `rm -rf "$INSTALL_DIR"` fully undoes this script.
#
# lib/ocr_metadata.py's find_tesseract() looks for a real `tesseract` on
# PATH first; this install is only the fallback for when there isn't one.
set -eu

INSTALL_DIR="${TESSERACT_LOCAL_INSTALL_DIR:-$HOME/.local/opt/tesseract-user}"
TESSERACT_BIN="$INSTALL_DIR/usr/bin/tesseract"

if [ -x "$TESSERACT_BIN" ]; then
    echo "Already installed: $TESSERACT_BIN"
    "$TESSERACT_BIN" --version | head -1
    exit 0
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "Downloading tesseract-ocr + tesseract-ocr-eng .debs (no install, no root)..."
( cd "$WORKDIR" && apt-get download tesseract-ocr tesseract-ocr-eng )

mkdir -p "$INSTALL_DIR"
for deb in "$WORKDIR"/*.deb; do
    dpkg-deb -x "$deb" "$INSTALL_DIR"
done

if [ ! -x "$TESSERACT_BIN" ]; then
    echo "Extraction finished but $TESSERACT_BIN is still missing - aborting." >&2
    exit 1
fi

TESSDATA_DIR="$(find "$INSTALL_DIR/usr/share/tesseract-ocr" -maxdepth 2 -type d -name tessdata | head -1)"
if [ -z "$TESSDATA_DIR" ] || [ ! -f "$TESSDATA_DIR/eng.traineddata" ]; then
    echo "Extraction finished but eng.traineddata is missing under $INSTALL_DIR - aborting." >&2
    exit 1
fi

echo "Installed: $TESSERACT_BIN"
TESSDATA_PREFIX="$TESSDATA_DIR" "$TESSERACT_BIN" --version | head -1
echo "tessdata: $TESSDATA_DIR"
