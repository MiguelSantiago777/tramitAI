"""Capturas dos manuais (dev, escritório de demonstração) + posição dos elementos destacados.

Uso (no container do vídeo): python3 capture_manuais.py
Saída: work/manuais/<tela>.png e work/manuais/boxes.json
"""

import json
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

BASE = "http://localhost:4200"
HOST_IP = "host.docker.internal"
SCALE = 1.2
OUT = Path("work/manuais")
OUT.mkdir(parents=True, exist_ok=True)

api = httpx.Client(base_url=f"http://{HOST_IP}:4200", timeout=30, headers={"Host": "localhost:4200"})
login = api.post(
    "/api/v1/auth/login/", json={"email": "video@tramitai.local", "password": "video-senha-123"}
).json()
auth = {"Authorization": f"Bearer {login['access']}"}
conversations = api.get("/api/v1/conversations/", headers=auth).json()["results"]
joao = next(c for c in conversations if c["contact_name"].startswith("João"))
maria_conv = next(c for c in conversations if c["contact_name"].startswith("Maria"))
maria = api.get("/api/v1/clients/", headers=auth, params={"q": "Maria"}).json()["results"][0]
case = api.get("/api/v1/cases/", headers=auth).json()["results"]
case_maria = next(c for c in case if "aposentadoria" in (c.get("assunto") or "").lower())

# nome: (caminho, [cliques antes da foto], rolar até, {alvo: seletor})
SHOTS: dict[str, tuple[str, list[str], str | None, dict[str, str]]] = {
    "login": ("/login", [], None, {"email": "input[type=email]", "entrar": "button[type=submit]"}),
    "inicio": (
        "/",
        [],
        None,
        {
            "menu": "nav, .sidebar, aside >> nth=0",
            "resumo": ".stats",
            "mesa": ".desk",
            "fila": "a:has-text('Revisar fila')",
        },
    ),
    "whatsapp": (
        "/configuracoes/whatsapp",
        [],
        None,
        {"estado": ".wa"},
    ),
    "termo": ("/configuracoes/termo", [], None, {"texto": ".term-text, .form-card >> nth=0"}),
    "conversa_joao": (
        f"/inbox/{joao['id']}",
        [],
        None,
        {
            "lista": ".inbox__list, app-inbox .list >> nth=0",
            "lia": ".bubble--out >> nth=1",
            "responder": "textarea",
        },
    ),
    "conversa_maria": (
        f"/inbox/{maria_conv['id']}",
        [],
        None,
        {
            "rascunho": "app-draft-card >> nth=0",
            "aprovar": "button:has-text('Aprovar e enviar') >> nth=0",
            "rapidas": "button[aria-label*='Respostas'], button:has(.icon:text('bolt')) >> nth=0",
            "responsavel": "mat-select >> nth=0",
        },
    ),
    "aprovacoes": (
        "/aprovacoes",
        [],
        None,
        {"rascunho": ".draft >> nth=0", "aprovar": "button:has-text('Aprovar e enviar') >> nth=0"},
    ),
    "respostas": ("/configuracoes/respostas", [], None, {"lista": "main .card, main table >> nth=0"}),
    "clientes": (
        "/clientes",
        [],
        None,
        {
            "novo": "a:has-text('Novo cliente'), button:has-text('Novo cliente') >> nth=0",
            "busca": "input >> nth=0",
            "tabela": "table, .table-card >> nth=0",
        },
    ),
    "cliente_ficha_topo": (
        f"/clientes/{maria['id']}",
        [],
        None,
        {"dados": "form >> nth=0"},
    ),
    "cliente_ficha": (
        f"/clientes/{maria['id']}",
        [],
        "app-client-fees-panel",
        {
            "historico": "app-client-timeline",
            "honorarios": "app-client-fees-panel",
            "documentos": "app-documents-panel",
        },
    ),
    "cliente_documentos": (
        f"/clientes/{maria['id']}",
        [],
        "app-documents-panel",
        {"enviar": "button:has-text('Enviar arquivo')", "lista": ".docs__list"},
    ),
    "processos": (
        "/processos",
        [],
        None,
        {
            "novo": "a:has-text('Novo processo'), button:has-text('Novo processo') >> nth=0",
            "tabela": "table, .table-card >> nth=0",
        },
    ),
    "processo": (
        f"/processos/{case_maria['id']}",
        [],
        "app-case-movements",
        {"andamentos": "app-case-movements"},
    ),
    "agenda": (
        "/agenda",
        [],
        None,
        {
            "google": "app-google-calendar-card",
            "pendentes": ".pending",
            "confirmar": ".pending button:has-text('Confirmar')",
            "semana": ".week",
            "novo": "button:has-text('Novo compromisso')",
        },
    ),
    "agenda_novo": (
        "/agenda",
        ["button:has-text('Novo compromisso')"],
        None,
        {"formulario": "mat-dialog-container", "responsavel": "mat-dialog-container mat-select >> nth=-1"},
    ),
    "tarefas": ("/tarefas", [], None, {"filtros": ".filters", "lista": ".task-list"}),
    "funil": ("/funil", [], None, {"quadro": ".board", "contratou": ".column >> nth=4"}),
    "financeiro": (
        "/financeiro",
        [],
        None,
        {
            "resumo": ".stats",
            "parcelas": ".row-list",
            "acoes": "app-installment-actions >> nth=1",
            "novo": "button:has-text('Novo contrato')",
        },
    ),
    "financeiro_contrato": (
        "/financeiro",
        ["button:has-text('Novo contrato')"],
        None,
        {"formulario": "mat-dialog-container"},
    ),
    "financeiro_menu": (
        "/financeiro",
        ["app-installment-actions >> nth=1 >> button"],
        None,
        {"menu": ".mat-mdc-menu-panel"},
    ),
    "mercadopago": ("/configuracoes/financeiro", [], None, {"cartao": ".form-card"}),
    "equipe": (
        "/configuracoes/equipe",
        [],
        None,
        {
            "convidar": "button:has-text('Convidar'), form >> nth=0",
            "membros": "table, .card >> nth=-1",
        },
    ),
    "configuracoes": (
        "/configuracoes/escritorio",
        [],
        "h2:has-text('Triagem automática')",
        {
            "triagem": "mat-slide-toggle[formcontrolname=auto_send_simple_replies]",
            "horario": ".hours",
            "agenda": "mat-slide-toggle[formcontrolname=scheduling_enabled]",
        },
    ),
    "relatorios": ("/relatorios", [], None, {"resumo": ".stats", "blocos": ".columns"}),
}


def box(page: Page, selector: str) -> list[int] | None:
    loc = page.locator(selector).first
    try:
        if loc.count() == 0:
            return None
        b = loc.bounding_box()
    except Exception:  # noqa: BLE001 - seletor alternativo inválido: segue
        return None
    if b is None:
        return None
    x1, y1 = max(b["x"], 0), max(b["y"], 0)
    x2, y2 = min(b["x"] + b["width"], 1600), min(b["y"] + b["height"], 900)
    if x2 <= x1 or y2 <= y1:
        return None
    return [round(v * SCALE) for v in (x1, y1, x2, y2)]


def new_page(browser):  # type: ignore[no-untyped-def]
    return browser.new_page(
        viewport={"width": 1600, "height": 900},
        device_scale_factor=SCALE,
        timezone_id="America/Sao_Paulo",
        locale="pt-BR",
    )


boxes: dict[str, dict[str, list[int]]] = {}
with sync_playwright() as p:
    browser = p.chromium.launch(
        args=[f"--host-resolver-rules=MAP localhost {HOST_IP}", "--lang=pt-BR"],
        env={"LANG": "pt_BR.UTF-8", "LANGUAGE": "pt_BR"},
    )
    page = new_page(browser)
    for name, (path, clicks, scroll_to, targets) in SHOTS.items():
        if name == "login":
            guest = new_page(browser)
            guest.goto(BASE + path)
            guest.wait_for_load_state("networkidle")
            guest.fill("input[type=email]", "dra.beatriz@silvalima.adv.br")
            guest.wait_for_timeout(600)
            current = guest
        else:
            if page.url == "about:blank":
                page.goto(BASE + "/login")
                page.evaluate(
                    "([a, r]) => { localStorage.setItem('tramitai.access', a);"
                    " localStorage.setItem('tramitai.refresh', r); }",
                    [login["access"], login["refresh"]],
                )
            page.goto(BASE + path)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1200)
            for selector in clicks:
                page.locator(selector).first.click()
                page.wait_for_timeout(900)
            if scroll_to:
                page.locator(scroll_to).first.evaluate(
                    "el => window.scrollBy(0, el.getBoundingClientRect().top - 90)"
                )
                page.wait_for_timeout(500)
            current = page
        current.screenshot(path=str(OUT / f"{name}.png"))
        boxes[name] = {}
        for target, selector in targets.items():
            for option in selector.split(", "):
                found = box(current, option)
                if found:
                    boxes[name][target] = found
                    break
            else:
                print(f"  aviso: {name}.{target} não encontrado")
        print("ok", name, list(boxes[name]))
        if current is not page:
            current.close()
        else:
            page.keyboard.press("Escape")  # fecha diálogo/menu aberto
    browser.close()

(OUT / "boxes.json").write_text(json.dumps(boxes, indent=1), encoding="utf-8")
