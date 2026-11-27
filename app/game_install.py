"""Find the installed game without relying on the build machine's paths."""

import os
import re
from pathlib import Path


STREAMING_ASSETS = Path('NarakaBladepoint_Data', 'StreamingAssets')


def streaming_assets(folder):
    """Accept either the game installation folder or its StreamingAssets folder."""
    folder = Path(folder).expanduser().resolve()
    for candidate in (folder / STREAMING_ASSETS, folder):
        if ((candidate / 'AppRes.info').is_file()
                and (candidate.parent.parent / 'NarakaBladepoint.exe').is_file()):
            return candidate
    return None


def steam_installations():
    """Return Steam installations across all configured libraries."""
    if os.name != 'nt':
        return []

    import winreg

    steam_roots = set()
    for hive, key, value in (
        (winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
        (winreg.HKEY_LOCAL_MACHINE, r'Software\WOW6432Node\Valve\Steam', 'InstallPath'),
    ):
        try:
            with winreg.OpenKey(hive, key) as handle:
                steam_roots.add(Path(winreg.QueryValueEx(handle, value)[0]))
        except OSError:
            continue

    libraries = set(steam_roots)
    for root in steam_roots:
        try:
            config = (root / 'steamapps' / 'libraryfolders.vdf').read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError):
            continue
        for path in re.findall(r'"path"\s+"([^"]+)"', config, flags=re.IGNORECASE):
            libraries.add(Path(path.replace('\\\\', '\\')))

    installations = set()
    for library in libraries:
        steamapps = library / 'steamapps'
        try:
            manifest = (steamapps / 'appmanifest_1203220.acf').read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError):
            continue
        match = re.search(r'"installdir"\s+"([^"]+)"', manifest, flags=re.IGNORECASE)
        if match:
            folder = streaming_assets(steamapps / 'common' / match[1])
            if folder:
                installations.add(folder)
    return sorted(installations)
