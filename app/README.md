# Atelier source and local build notes

This repository carries the Atelier Python application, vendor codec source, and web UI. The installed executable and build environment are not committed.

The current code targets catalogue/client version 1.5.9.2. A fresh checkout does not contain `app/resources`; the application cannot start until a compatible local resource pack is prepared. That pack includes a catalogue export, native table/rule metadata, a schema, and pristine baseline data and hashes from the target PC's own Naraka installation. This repository intentionally excludes those generated files, extracted game data, and the existing machine's install-specific manifest/profile. Do not reuse another PC's resource baseline; the app verifies the local game build and baseline before applying changes.

Install Python dependencies with `py -m pip install -r app/requirements.txt`. The app requires Windows and WebView2 for its native window. `app/package_app.py` builds an onedir package after the local resource pack has been prepared. Its catalogue version must match the version pinned by the native metadata. Keep generated resources, backups, output builds, and user selections outside Git.

Atelier edits local presentation resources only. It does not change account ownership, purchases, currency, or network state. A game update requires a fresh resource review and compatibility verification before use.
