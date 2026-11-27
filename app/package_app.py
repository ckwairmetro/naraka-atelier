"""Build a portable Windows distribution from a prepared resource pack."""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from core import COMMON, sha_file


def main():
    root = Path(__file__).resolve().parent
    resources = root / 'resources'
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalogue', type=Path, default=resources / 'catalogue.zip')
    parser.add_argument('--output', type=Path, default=root.parent / 'NarakaAtelier-install')
    parser.add_argument('--version', help='Application version recorded in the packaged manifest')
    args = parser.parse_args()

    manifest = json.loads((resources / 'build.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(args.catalogue) as archive:
        data = archive.read('naraka-catalogue/data.js').decode('utf-8').strip()
    prefix = 'window.CATALOG = '
    if not data.startswith(prefix) or not data.endswith(';'):
        raise ValueError('Unsupported catalogue format')
    catalogue = json.loads(data[len(prefix):-1])
    if catalogue['gameVersion']['clientVersion'] != manifest['catalogue_version']:
        raise ValueError('Catalogue build does not match packaged native adapters')

    for name in ('AppRes.info', COMMON, 'e/5/e50ef81ba77ae51a'):
        if sha_file(resources / 'baseline' / name) != manifest['initial_installed'][name]:
            raise ValueError('Baseline does not match the release manifest: ' + name)

    if json.loads((resources / 'active.json').read_text(encoding='utf-8')):
        raise ValueError('The release baseline contains saved cosmetic selections')

    manifest.pop('game', None)
    manifest.pop('previous_stack', None)
    manifest.pop('rebase_history', None)
    if args.version:
        manifest['application_version'] = args.version

    with tempfile.TemporaryDirectory(prefix='atelier-package-') as directory:
        staging = Path(directory)
        packaged = staging / 'resources'
        shutil.copytree(
            resources, packaged,
            ignore=shutil.ignore_patterns(
                'build.json', 'catalogue.zip', 'pristine_AppRes.info', 'native_rows.v01.json.gz',
            ),
        )
        shutil.copyfile(args.catalogue, packaged / 'catalogue.zip')
        (packaged / 'build.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        vendor = staging / 'vendor'
        shutil.copytree(root / 'vendor', vendor, ignore=shutil.ignore_patterns('__pycache__'))

        command = [
            sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--noconsole',
            '--name', 'NarakaAtelier', '--distpath', str(args.output.resolve()),
            '--workpath', str(staging / 'build'), '--specpath', str(staging),
            '--paths', str(root / 'vendor'), '--collect-all', 'UnityPy', '--collect-all', 'lz4',
        ]
        for module in ('pandas', 'scipy', 'matplotlib', 'torch', 'sklearn', 'IPython', 'pytest', 'playwright'):
            command += ['--exclude-module', module]
        for source in (packaged, root / 'web', vendor):
            command += ['--add-data', str(source) + ';' + source.name]
        command.append(str(root / 'main.py'))
        subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
