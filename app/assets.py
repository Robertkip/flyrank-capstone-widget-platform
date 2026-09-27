"""Versioned widget delivery. The bundle URL contains a content hash, so a new release = a new URL,
which lets it be cached for a year. The tiny loader at /widget.js is cached briefly and points at the current bundle."""
import hashlib
import json
import os
from .config import settings

_src = open(os.path.join(os.path.dirname(__file__), "static", "widget.js"), "rb").read()
BUNDLE_HASH = hashlib.sha256(_src).hexdigest()[:12]
BUNDLE_PATH = f"/assets/widget-{BUNDLE_HASH}.js"
BUNDLE = _src


def loader_js(widget_id: str) -> str:
    """Loader for the one-line snippet: <script src=".../widget.js?id=ID"></script>.
    It tags itself with the widget id and pulls the versioned bundle once per page."""
    return (
        "(function(){var s=document.currentScript;"
        f"window.__LEAD_WIDGET_API__={json.dumps(settings.public_base_url)};"
        f"if(s)s.setAttribute('data-lead-widget',{json.dumps(widget_id)});"
        "if(window.__leadWidgetScan){window.__leadWidgetScan();return;}"
        f"if(!document.querySelector('script[data-lead-bundle]')){{var b=document.createElement('script');"
        f"b.src={json.dumps(settings.public_base_url + BUNDLE_PATH)};b.async=true;b.setAttribute('data-lead-bundle','');"
        "document.head.appendChild(b);}})();")


def snippet(public_id: str) -> str:
    return f'<script src="{settings.public_base_url}/widget.js?id={public_id}" async></script>'
