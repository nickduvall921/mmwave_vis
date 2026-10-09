"""The page's files are served from /assets, never /static.

Before 2026.10, Home Assistant's service worker caches any URL with /static/ in it,
ingress included, on first load, ignoring the query string, and never refreshes it
(home-assistant/frontend#54707). A phone that opened the addon once kept running that
version's CSS and JavaScript under every newer page.
"""
import os
import re

ADDON = os.path.join(os.path.dirname(__file__), '..', 'mmwave_vis')


def _read(*parts):
    with open(os.path.join(ADDON, *parts), encoding='utf-8') as f:
        return f.read()


def test_flask_serves_files_from_assets():
    assert re.search(r"Flask\(__name__,\s*static_url_path='/assets'\)", _read('app.py'))


def test_page_links_only_to_assets_that_exist():
    html = _read('templates', 'index.html')
    assert '/static/' not in html
    links = re.findall(r'\{\{ ingress_path \}\}/assets/([^"?]+)', html)
    assert 'app.css' in links and 'js/main.js' in links
    for path in links:
        assert os.path.isfile(os.path.join(ADDON, 'static', path)), path


def test_every_module_is_preloaded():
    html = _read('templates', 'index.html')
    preloaded = set(re.findall(r'rel="modulepreload" href="\{\{ ingress_path \}\}/assets/js/([^"]+)"', html))
    modules = {f for f in os.listdir(os.path.join(ADDON, 'static', 'js')) if f.endswith('.js')} - {'main.js'}
    assert preloaded == modules
