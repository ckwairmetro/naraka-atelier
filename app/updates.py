"""Read the release channel without downloading or running an installer."""

import json
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


_VERSION = re.compile(r'[0-9]{1,6}(?:\.[0-9]{1,6}){2,3}')
_INSTALLER = re.compile(r'NarakaAtelier-v[0-9.]+-Setup-x64\.exe')
_MAX_FEED_SIZE = 4096


def version_number(value):
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise ValueError('Invalid Atelier version')
    parts = tuple(map(int, value.split('.')))
    return parts + (0,) * (4 - len(parts))


def https_origin(url):
    address = urlsplit(url)
    if address.scheme != 'https' or not address.hostname or address.username is not None or address.fragment:
        raise ValueError('Atelier update feed must use a plain HTTPS URL')
    return address.hostname, address.port or 443


def check_updates(current, feed_url, release_page=None):
    fallback = {'current': current}
    if release_page:
        fallback['url'] = release_page
    if not feed_url:
        return dict(fallback, state='unconfigured')

    try:
        origin = https_origin(feed_url)
        request = Request(feed_url, headers={'Accept': 'application/json', 'Cache-Control': 'no-cache'})
        with urlopen(request, timeout=8) as response:
            if https_origin(response.geturl()) != origin:
                raise ValueError('Update feed redirected to a different host')
            raw = response.read(_MAX_FEED_SIZE + 1)
        if len(raw) > _MAX_FEED_SIZE:
            raise ValueError('Update feed is too large')

        release = json.loads(raw)
        if not isinstance(release, dict):
            raise ValueError('Invalid update feed')
        latest = release.get('version')
        installer = release.get('installer')
        if (not isinstance(installer, str) or not _INSTALLER.fullmatch(installer)
                or installer != f'NarakaAtelier-v{latest}-Setup-x64.exe'):
            raise ValueError('Invalid update installer name')
        download_page = release.get('download_page')
        if download_page is not None:
            if not isinstance(download_page, str):
                raise ValueError('Invalid update download page')
            https_origin(download_page)
        if version_number(latest) <= version_number(current):
            return {'current': current, 'latest': latest, 'state': 'current'}
        return {'current': current, 'latest': latest, 'state': 'available',
                'url': download_page or urljoin(feed_url, installer)}
    except (OSError, ValueError):
        return dict(fallback, state='unavailable')
