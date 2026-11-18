"""Gera o logo do TramitAI (o "T" no degradê da marca) em PNG quadrado."""

from playwright.sync_api import sync_playwright

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;width:%(s)spx;height:%(s)spx;background:transparent}
div{width:100%%;height:100%%;border-radius:22%%;display:grid;place-items:center;
background:linear-gradient(135deg,#4f46e5 0%%,#7c3aed 55%%,#0e7490 100%%);
color:#fff;font:800 %(f)spx/1 'Noto Sans',sans-serif}
</style></head><body><div>T</div></body></html>"""

with sync_playwright() as p:
    browser = p.chromium.launch()
    for size in (120, 512):
        page = browser.new_page(viewport={"width": size, "height": size})
        page.set_content(HTML % {"s": size, "f": int(size * 0.62)})
        page.screenshot(path=f"/marca/logo-{size}.png", omit_background=True)
        print("ok", size)
    browser.close()
