"""Captura as telas do sistema (dev) com o escritório de demonstração, em 1920x1080, e guarda
a posição dos elementos que a Lia vai destacar no vídeo (work/shots/boxes.json).

Uso (no container do vídeo): python3 capture.py [host]
"""

import json
import sys
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

# O dev server do Angular só aceita o nome "localhost": dentro do container, "localhost" é
# redirecionado para a máquina (host.docker.internal) no navegador e no httpx.
BASE = "http://localhost:4200"
HOST_IP = sys.argv[1] if len(sys.argv) > 1 else "host.docker.internal"
SCALE = 1.2  # 1600x900 CSS → 1920x1080 na imagem
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

# tela: (caminho, rolar até (seletor) ou None, {alvo: seletor})
# Seletores do Playwright: CSS, "text=..." ou com ">> nth=N".
PAGES: dict[str, tuple[str, str | None, dict[str, str]]] = {
    "inicio": ("/", None, {"resumo": ".stats", "mesa": ".desk"}),
    "conversa": (
        f"/inbox/{joao['id']}",
        None,
        {"aviso_horario": ".bubble--out >> nth=0", "triagem": ".bubble--out >> nth=1"},
    ),
    "agenda": (
        "/agenda",
        None,
        {"pendentes": ".pending", "confirmar": ".pending button:has-text('Confirmar')"},
    ),
    "aprovacoes": (
        "/aprovacoes",
        None,
        {"rascunho": ".draft >> nth=0", "aprovar": "button:has-text('Aprovar e enviar') >> nth=0"},
    ),
    "ficha": (
        f"/clientes/{maria['id']}",
        "app-client-fees-panel",
        {
            "historico": "app-client-timeline",
            "honorarios": "app-client-fees-panel",
            "documentos": "app-documents-panel",
        },
    ),
    "funil": ("/funil", None, {"quadro": ".board", "contratou": ".column >> nth=4"}),
    "financeiro": (
        "/financeiro",
        None,
        {
            "parcelas": ".row-list",
            "pix": "text=Pix gerado",
            "recebido": ".stat >> nth=0",
        },
    ),
    "relatorios": (
        "/relatorios",
        None,
        {"contatos": ".columns .panel-card >> nth=0", "recebido": ".stat >> nth=0"},
    ),
    "configuracoes": (
        "/configuracoes/escritorio",
        "h2:has-text('Triagem automática')",
        {
            "triagem": "mat-slide-toggle[formcontrolname=auto_send_simple_replies]",
            "horario": ".hours",
            "agenda": "mat-slide-toggle[formcontrolname=scheduling_enabled]",
        },
    ),
}


def box(page: Page, selector: str) -> list[int] | None:
    """Retângulo visível do elemento, em pixels da imagem (x1, y1, x2, y2)."""
    loc = page.locator(selector).first
    if loc.count() == 0:
        return None
    b = loc.bounding_box()
    if b is None:
        return None
    x1, y1 = max(b["x"], 0), max(b["y"], 0)
    x2, y2 = min(b["x"] + b["width"], 1600), min(b["y"] + b["height"], 900)
    if x2 <= x1 or y2 <= y1:
        return None
    return [round(v * SCALE) for v in (x1, y1, x2, y2)]


boxes: dict[str, dict[str, list[int]]] = {}
with sync_playwright() as p:
    browser = p.chromium.launch(
        args=[f"--host-resolver-rules=MAP localhost {HOST_IP}", "--lang=pt-BR"],
        env={"LANG": "pt_BR.UTF-8", "LANGUAGE": "pt_BR"},
    )
    page = browser.new_page(
        viewport={"width": 1600, "height": 900},
        device_scale_factor=SCALE,
        timezone_id="America/Sao_Paulo",
        locale="pt-BR",
    )
    page.goto(BASE + "/login")
    page.evaluate(
        "([a, r]) => { localStorage.setItem('tramitai.access', a);"
        " localStorage.setItem('tramitai.refresh', r); }",
        [login["access"], login["refresh"]],
    )
    for name, (path, scroll_to, targets) in PAGES.items():
        page.goto(BASE + path)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        if scroll_to:
            page.locator(scroll_to).first.evaluate(
                "el => window.scrollBy(0, el.getBoundingClientRect().top - 90)"
            )
            page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / f"{name}.png"))
        boxes[name] = {}
        for target, selector in targets.items():
            found = box(page, selector)
            if found:
                boxes[name][target] = found
            else:
                print(f"  aviso: {name}.{target} não encontrado ({selector})")
        print("ok", name, list(boxes[name]))
    browser.close()

(OUT / "boxes.json").write_text(json.dumps(boxes, indent=1), encoding="utf-8")
