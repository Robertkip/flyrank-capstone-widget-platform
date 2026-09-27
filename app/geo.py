"""IP -> geolocation with a provider fallback chain. Degrade, never fail: returns None if every provider is down."""
import ipaddress
import logging
import httpx
from .config import settings

log = logging.getLogger("geo")
# Toggle for the deterministic mock providers (probe 4). Real providers ignore it.
MOCK_DOWN: set[str] = set()


class ProviderDown(Exception):
    pass


def _mock_a(ip):
    if "mock_a" in MOCK_DOWN:
        raise ProviderDown("mock_a is toggled down")
    return {"country": "Kenya", "country_code": "KE", "city": "Nairobi"}


def _mock_b(ip):
    if "mock_b" in MOCK_DOWN:
        raise ProviderDown("mock_b is toggled down")
    return {"country": "Kenya", "country_code": "KE", "city": "Kisii"}


def _ip_api(ip):          # ip-api.com - free, no key, 45 req/min (HTTP only on the free tier)
    r = httpx.get(f"http://ip-api.com/json/{ip}", params={"fields": "status,message,country,countryCode,city"},
                  timeout=settings.geo_timeout_s)
    d = r.json()
    if r.status_code != 200 or d.get("status") != "success":
        raise ProviderDown(f"ip-api: {d.get('message', r.status_code)}")
    return {"country": d["country"], "country_code": d["countryCode"], "city": d.get("city")}


def _ipapi_co(ip):        # ipapi.co - free tier ~1,000/day, no key
    r = httpx.get(f"https://ipapi.co/{ip}/json/", timeout=settings.geo_timeout_s, headers={"User-Agent": "widget-platform/1.0"})
    d = r.json()
    if r.status_code != 200 or d.get("error"):
        raise ProviderDown(f"ipapi.co: {d.get('reason', r.status_code)}")
    return {"country": d.get("country_name"), "country_code": d.get("country_code"), "city": d.get("city")}


PROVIDERS = {"mock_a": _mock_a, "mock_b": _mock_b, "ip-api": _ip_api, "ipapi-co": _ipapi_co}


def lookup(ip: str) -> dict | None:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    uses_real = any(not p.startswith("mock") for p in settings.geo_chain)
    if uses_real and (addr.is_private or addr.is_loopback):
        return None          # real providers can't locate private/loopback IPs; skip the network calls
    for name in settings.geo_chain:
        fn = PROVIDERS.get(name)
        if not fn:
            continue
        try:
            res = fn(ip)
            return {**res, "provider": name}
        except (ProviderDown, httpx.HTTPError, ValueError, KeyError) as e:
            log.warning("geo provider %s failed: %s -> trying next", name, e)
    log.warning("all geo providers failed for this submission; storing without geo")
    return None
