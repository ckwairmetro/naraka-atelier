# Naraka Atelier source

This private repository contains the Atelier application source and its web UI. It does not include the packaged executable, local profiles, reports, Naraka asset dumps, or extracted game resource baseline.

## Requirements

- Windows 10/11
- Python 3.11 or newer
- A local Naraka installation matching the resource catalogue version
- WebView2 Runtime for the native app window

Install Python dependencies with `py -m pip install -r app/requirements.txt`. The checked-in Python source is not a ready-to-run build by itself: Atelier expects a generated `app/resources` pack, including a catalogue, native table metadata, and a pristine baseline captured from the destination PC's own game installation. Keep that pack local. The resource pack is deliberately omitted here because it contains extracted Naraka data and install-specific hashes. See `app/README.md` for the build boundary and current pinned client version.

The packaged build can be produced with PyInstaller after preparing that local resource pack. Do not copy a saved profile or another computer's baseline over the destination installation.
