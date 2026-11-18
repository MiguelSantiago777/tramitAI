"""Captura as telas do sistema (dev) com o escritório de demonstração, em 1920x1080.

Uso (no container do vídeo): python capture.py http://host.docker.internal:4200
"""

import sys
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

# O dev server do Angular só aceita o nome "localhost": dentro do container, "localhost" é
# redirecionado para a máquina (host.docker.internal) no navegador e no httpx.
BASE = "http://localhost:4200"
HOST_IP = sys.argv[1] if len(sys.argv) > 1 else "host.docker.internal"
OUT = Path("work/shots")
OUT.mkdir(parents=True, exist_ok=True)

api = httpx.Client(
    base_url=f"http://{HOST_IP}:4200", timeout=30, headers={"Host": "localhost:4200"}
)
login = api.post(
    "/api/v1/auth/login/", json={"email": "video@tramitai.local", "password": "video-senha-123"}
).json()
headers = {"Authorization": f"Bearer {login['access']}"}
clients = api.get("/api/v1/clients/", headers=headers, params={"q": "Maria"}).json()["results"]
conversations = api.get("/api/v1/conversations/", headers=headers).json()["results"]
joao = next(c for c in conversations if c["contact_name"].startswith("João"))
maria = clients[0]

PAGES = {
    "inicio": "/",
    "conversa": f"/inbox/{joao['id']}",
    "agenda": "/agenda",
    "aprovacoes": "/aprovacoes",
    "ficha": f"/clientes/{maria['id']}",
    "funil": "/funil",
    "financeiro": "/financeiro",
    "relatorios": "/relatorios",
    "configuracoes": "/configuracoes/escritorio",
}

with sync_playwright() as p:
    browser = p.chromium.launch(
        args=[f"--host-resolver-rules=MAP localhost {HOST_IP}"]
    )
    page = browser.new_page(
        viewport={"width": 1600, "height": 900},
        device_scale_factor=1.2,
        timezone_id="America/Sao_Paulo",
        locale="pt-BR",
    )
    page.goto(BASE + "/login")
    page.evaluate(
        "([a, r]) => { localStorage.setItem('tramitai.access', a);"
        " localStorage.setItem('tramitai.refresh', r); }",
        [login["access"], login["refresh"]],
    )
    for name, path in PAGES.items():
        page.goto(BASE + path)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        if name == "ficha":
            # Ficha do cliente: rola até o histórico, honorários e documentos.
            page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.45)")
            page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / f"{name}.png"))
        print("ok", name)
    browser.close()
