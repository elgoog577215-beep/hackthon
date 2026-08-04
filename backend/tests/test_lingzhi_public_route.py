import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "configure_lingzhi_public_route.py"

LEGACY_CADDYFILE = """tuotuzju.com, www.tuotuzju.com {
\troute {
\t\t@lingzhi_exact path /lingzhi /lingzhi/
\t\thandle @lingzhi_exact {
\t\t\tredir https://lingzhi.tuotuzju.com/ 302
\t\t}

\t\t@lingzhi_path path_regexp lingzhi_path ^/lingzhi/(.*)$
\t\thandle @lingzhi_path {
\t\t\tredir https://lingzhi.tuotuzju.com/{re.lingzhi_path.1} 302
\t\t}

\t\thandle {
\t\t\trespond "main"
\t\t}
\t}
}

lingzhi.tuotuzju.com {
\troute {
\t\trequest_body {
\t\t\tmax_size 1024MB
\t\t}

\t\thandle {
\t\t\theader X-Proxy-Source "Lingzhi-7862"
\t\t\treverse_proxy 127.0.0.1:7862
\t\t}
\t}
}
"""


def load_route_module():
    assert SCRIPT.exists(), "public-route configurator is missing"
    spec = importlib.util.spec_from_file_location("configure_lingzhi_public_route", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rewrite_keeps_lingzhi_on_the_main_domain() -> None:
    module = load_route_module()

    rewritten = module.rewrite_caddyfile(LEGACY_CADDYFILE)

    assert "@lingzhi_exact path /lingzhi" in rewritten
    assert "redir /lingzhi/ 308" in rewritten
    assert "@lingzhi_path path /lingzhi/*" in rewritten
    assert "uri strip_prefix /lingzhi" in rewritten
    assert "reverse_proxy 127.0.0.1:7862" in rewritten
    assert "redir https://tuotuzju.com/lingzhi{uri} 308" in rewritten
    assert "redir https://lingzhi.tuotuzju.com/" not in rewritten


def test_rewrite_is_idempotent() -> None:
    module = load_route_module()

    rewritten = module.rewrite_caddyfile(LEGACY_CADDYFILE)

    assert module.rewrite_caddyfile(rewritten) == rewritten


def test_rewrite_rejects_an_unknown_route_shape() -> None:
    module = load_route_module()

    with pytest.raises(ValueError, match="Lingzhi"):
        module.rewrite_caddyfile("tuotuzju.com { respond \"main\" }\n")
