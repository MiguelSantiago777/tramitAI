"""Manuais em vídeo do TramitAI (aba Manuais do sistema): um vídeo curto por assunto.

Reaproveita a montagem do make_video.py (voz da Vera, legendas, destaque sincronizado com a
fala) com mais compressão, para servir os vídeos pelo próprio sistema.

Uso (no container do vídeo, depois do capture_manuais.py):
    python3 make_manuais.py            # todos
    python3 make_manuais.py agenda     # só um
Saída: out/manuais/<id>.mp4, <id>.jpg (capa) e manuais.json (título, descrição, duração).
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

import make_video as mv

mv.SHOTS = Path("work/manuais")
mv.CRF = 27
mv.AUDIO_BITRATE = "96k"
OUT = Path("out/manuais")
OUT.mkdir(parents=True, exist_ok=True)

# id, título, descrição curta (aparece na aba Manuais), cenas:
#   (imagem, rótulo no canto, narração, [(trecho da fala, alvo destacado)])
MANUAIS = [
    (
        "primeiros-passos",
        "Primeiros passos",
        "Como entrar, a tela inicial e onde fica cada coisa.",
        [
            (
                "login",
                "Entrar",
                "Para entrar, acesse app ponto tramitai ponto pro, digite o seu e-mail e a sua "
                "senha e clique em Entrar. Se esquecer a senha, use o link Esqueci minha senha.",
                [("seu e-mail", "email"), ("clique em Entrar", "entrar")],
            ),
            (
                "inicio",
                "Tela inicial",
                "Na tela inicial você vê o resumo do dia. Os números no topo mostram o que precisa "
                "da sua atenção, como mensagens esperando aprovação. Em Minha mesa ficam os seus "
                "compromissos e tarefas de hoje. Para revisar as minhas mensagens, clique em "
                "Revisar fila.",
                [
                    ("números no topo", "resumo"),
                    ("Minha mesa", "mesa"),
                    ("Revisar fila", "fila"),
                ],
            ),
            (
                "inicio",
                "O menu",
                "No menu à esquerda ficam todas as áreas do sistema: conversas, aprovações, "
                "clientes, processos, agenda, financeiro e as configurações do escritório. E "
                "sempre que tiver dúvida, os manuais ficam na aba Manuais.",
                [("menu à esquerda", "menu")],
            ),
        ],
    ),
    (
        "whatsapp",
        "WhatsApp e termo de IA",
        "Conectar o número do escritório e o termo de ciência de IA.",
        [
            (
                "whatsapp",
                "Conectar o WhatsApp",
                "Em WhatsApp, você conecta o número do escritório. Clique em Conectar e leia o QR "
                "Code com o celular do escritório, em Aparelhos conectados, como no WhatsApp Web. "
                "Quando aparecer Conectado, as mensagens dos clientes começam a chegar aqui.",
                [("aparecer Conectado", "estado")],
            ),
            (
                "termo",
                "Termo de IA",
                "Em Termo de IA fica o texto que eu envio no primeiro contato de cada pessoa. Ela "
                "só conversa comigo depois de responder aceito. Você pode ajustar o texto quando "
                "quiser. Quem aceitou a versão anterior recebe a nova para aceitar de novo.",
                [("o texto que eu envio", "texto")],
            ),
        ],
    ),
    (
        "conversas",
        "Conversas e a Vera",
        "Triagem pela Vera, aprovação de mensagens e respostas prontas.",
        [
            (
                "conversa_joao",
                "Conversas",
                "Em Conversas ficam todas as mensagens do WhatsApp. À esquerda, a lista. À "
                "direita, a conversa aberta. Com a triagem automática ligada, eu converso sozinha "
                "com contatos novos: pergunto o nome e entendo o caso. As minhas mensagens "
                "aparecem com o nome Vera.",
                [("a lista", "lista"), ("aparecem com o nome Vera", "lia")],
            ),
            (
                "conversa_maria",
                "Aprovar a resposta",
                "Para quem já é cliente, eu escrevo a resposta e ela fica aqui, esperando você. "
                "Leia, ajuste o texto se quiser e clique em Aprovar e enviar. Para responder você "
                "mesma, escreva no campo de baixo. O raio abre as respostas prontas. E em "
                "Responsável você define quem da equipe cuida da conversa.",
                [
                    ("eu escrevo a resposta", "rascunho"),
                    ("Aprovar e enviar", "aprovar"),
                    ("respostas prontas", "rapidas"),
                    ("em Responsável", "responsavel"),
                ],
            ),
            (
                "aprovacoes",
                "Aprovações",
                "A tela Aprovações junta todas as mensagens esperando o seu ok, de todas as "
                "conversas, inclusive os avisos de andamento de processo e os lembretes. É um bom "
                "lugar para começar o dia.",
                [("todas as mensagens esperando o seu ok", "rascunho")],
            ),
            (
                "respostas",
                "Respostas prontas",
                "E em Respostas prontas você cadastra os textos que a equipe usa sempre, como a "
                "lista de documentos ou o endereço do escritório.",
                [("cadastra os textos", "lista")],
            ),
        ],
    ),
    (
        "clientes-processos",
        "Clientes, processos e documentos",
        "Cadastro, ficha do cliente, documentos e acompanhamento de processos.",
        [
            (
                "clientes",
                "Clientes",
                "Em Clientes você encontra todos os seus clientes. Use a busca por nome, CPF ou "
                "telefone, ou clique em Novo cliente para cadastrar.",
                [("Use a busca", "busca"), ("Novo cliente", "novo")],
            ),
            (
                "cliente_ficha_topo",
                "Ficha do cliente",
                "Na ficha do cliente ficam os dados de contato e as etiquetas, que ajudam a "
                "separar os clientes por assunto.",
                [("dados de contato", "dados")],
            ),
            (
                "cliente_ficha",
                "Tudo num lugar só",
                "Logo abaixo, o histórico mostra tudo o que aconteceu com o cliente: mensagens, "
                "andamentos, tarefas e atendimentos. Depois vêm os honorários e os documentos.",
                [
                    ("o histórico", "historico"),
                    ("os honorários", "honorarios"),
                    ("os documentos", "documentos"),
                ],
            ),
            (
                "cliente_documentos",
                "Documentos",
                "Para guardar um arquivo, clique em Enviar arquivo ou arraste para cá. E o que o "
                "cliente manda pelo WhatsApp, como fotos, áudios e PDFs, entra sozinho nesta pasta.",
                [("Enviar arquivo", "enviar"), ("entra sozinho nesta pasta", "lista")],
            ),
            (
                "processos",
                "Processos",
                "Em Processos, clique em Novo processo e informe o número CNJ. O sistema "
                "identifica o tribunal e passa a acompanhar os andamentos sozinho.",
                [("Novo processo", "novo")],
            ),
            (
                "processo",
                "Andamentos",
                "Quando sai um andamento novo, ele aparece aqui. Eu escrevo um aviso em português "
                "simples para o cliente, e ele vai para a sua aprovação antes de sair.",
                [("ele aparece aqui", "andamentos")],
            ),
        ],
    ),
    (
        "agenda",
        "Agenda, tarefas e Google Agenda",
        "Compromissos, consultas marcadas pela Vera, tarefas e Google Agenda.",
        [
            (
                "agenda",
                "Agenda",
                "Na Agenda você vê a semana do escritório. Para marcar, clique em Novo "
                "compromisso.",
                [("a semana do escritório", "semana"), ("Novo compromisso", "novo")],
            ),
            (
                "agenda_novo",
                "Novo compromisso",
                "Preencha o tipo, o título, a data e o horário. No campo Responsável, escolha quem "
                "vai atender: é na agenda dessa pessoa que o compromisso aparece, inclusive no "
                "Google Agenda dela. Se escolher o cliente, dá para ligar o lembrete pelo WhatsApp "
                "na véspera.",
                [("Preencha o tipo", "formulario"), ("No campo Responsável", "responsavel")],
            ),
            (
                "agenda",
                "Consultas da Vera",
                "As consultas que eu marco pelo WhatsApp aparecem no topo, como a confirmar. "
                "Clique em Confirmar e o cliente recebe a confirmação na hora.",
                [("como a confirmar", "pendentes"), ("Clique em Confirmar", "confirmar")],
            ),
            (
                "agenda",
                "Google Agenda",
                "Se você usa o Google Agenda, clique em Conectar e autorize a sua conta. O que for "
                "marcado aqui vai para o seu Google, e eu não ofereço horários em que você já tem "
                "compromisso por lá.",
                [("clique em Conectar", "google")],
            ),
            (
                "tarefas",
                "Tarefas e prazos",
                "Em Tarefas e prazos ficam as pendências da equipe, com responsável e data. Use os "
                "filtros para ver só as suas, as atrasadas ou as de hoje.",
                [("as pendências da equipe", "lista"), ("Use os filtros", "filtros")],
            ),
        ],
    ),
    (
        "funil",
        "Funil de clientes",
        "Acompanhar quem chegou até virar contrato.",
        [
            (
                "funil",
                "Funil",
                "O funil mostra os contatos novos em cada etapa, do primeiro contato até a "
                "proposta. Quem chega pelo WhatsApp entra aqui sozinho. Para mudar de etapa, "
                "arraste o cartão para a coluna seguinte. Quando a pessoa fechar, mova para "
                "Contratou.",
                [("em cada etapa", "quadro"), ("mova para Contratou", "contratou")],
            ),
        ],
    ),
    (
        "financeiro",
        "Financeiro e Mercado Pago",
        "Honorários em parcelas, Pix, link de pagamento e baixa automática.",
        [
            (
                "mercadopago",
                "Mercado Pago",
                "Primeiro, conecte a conta do Mercado Pago do escritório, em Configurações, "
                "Mercado Pago, colando o Access Token. O dinheiro das cobranças cai direto na sua "
                "conta.",
                [("conecte a conta", "cartao")],
            ),
            (
                "financeiro_contrato",
                "Novo contrato",
                "Para cadastrar honorários, clique em Novo contrato. Escolha o cliente, o valor "
                "total, a entrada, se houver, o número de parcelas e o primeiro vencimento. O "
                "sistema mostra as parcelas antes de salvar.",
                [("Escolha o cliente", "formulario")],
            ),
            (
                "financeiro",
                "Acompanhar",
                "Nesta tela você acompanha o mês: quanto recebeu, quanto está previsto e o que "
                "está em atraso. Abaixo, todas as parcelas.",
                [("acompanha o mês", "resumo"), ("todas as parcelas", "parcelas")],
            ),
            (
                "financeiro_menu",
                "Cobrar",
                "No menu de cada parcela, você gera um Pix ou um link de pagamento e envia a "
                "cobrança pelo WhatsApp. Quando o cliente paga pelo Mercado Pago, a parcela "
                "recebe baixa sozinha. Se ele pagar de outro jeito, use Dar baixa.",
                [("No menu de cada parcela", "menu")],
            ),
        ],
    ),
    (
        "equipe-configuracoes",
        "Equipe e configurações",
        "Convidar a equipe, horário de atendimento e como a Vera trabalha.",
        [
            (
                "equipe",
                "Equipe",
                "Em Equipe você convida as pessoas do escritório pelo e-mail. Cada uma recebe um "
                "link para criar a senha. Advogados podem aprovar mensagens. A equipe "
                "administrativa usa o sistema normalmente, mas só aprova se você liberar.",
                [("convida as pessoas", "convidar"), ("Advogados podem aprovar", "membros")],
            ),
            (
                "configuracoes",
                "Como a Vera trabalha",
                "Em Configurações do escritório você decide como eu trabalho: se posso fazer a "
                "triagem sozinha com contatos novos, o horário de atendimento e se posso oferecer "
                "horários na agenda para a consulta inicial. Depois, é só clicar em Salvar.",
                [
                    ("triagem sozinha", "triagem"),
                    ("o horário de atendimento", "horario"),
                    ("oferecer horários na agenda", "agenda"),
                ],
            ),
            (
                "relatorios",
                "Relatórios",
                "E em Relatórios você acompanha os números do período: contatos, contratos, "
                "atendimento, processos e financeiro. Qualquer dúvida, volte aqui nos Manuais "
                "quando quiser.",
                [("os números do período", "resumo")],
            ),
        ],
    ),
]

CARD = (
    '<p style="font-size:34px;letter-spacing:.08em;text-transform:uppercase;opacity:.8;'
    'margin:56px 0 0">Manual {n} de {total}</p><h1 style="margin-top:16px">{title}</h1>'
    "<p>{desc}</p>"
)


def render_card(manual_id: str, n: int, title: str, desc: str) -> None:
    body = CARD.format(n=n, total=len(MANUAIS), title=title, desc=desc)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.set_content(mv.CARD_HTML.replace("{body}", body))
        page.screenshot(path=str(mv.WORK / "cards" / f"{manual_id}.png"))
        browser.close()


def build(n: int, manual: tuple) -> dict:
    manual_id, title, desc, scenes = manual
    render_card(manual_id, n, title, desc)
    intro = (
        f"intro-{manual_id}",
        f"card:{manual_id}",
        "",
        f"Manual {n}: {title}.",
        [],
    )
    full = [intro] + [
        (f"{manual_id}-{i:02d}", image, label, text, highlights)
        for i, (image, label, text, highlights) in enumerate(scenes, 1)
    ]
    boxes = json.loads((mv.SHOTS / "boxes.json").read_text(encoding="utf-8"))
    parts, total = [], 0.0
    for i, scene in enumerate(full):
        words = asyncio.run(mv.speak(scene[0], scene[3]))
        path, seconds, _ = mv.render_scene(i, scene, words, boxes)
        parts.append(path)
        total += seconds
    listing = mv.WORK / "scenes" / f"lista-{manual_id}.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    video = OUT / f"{manual_id}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(video),
        ],
        check=True,
    )
    mv.add_music(video, seed=n)  # cada manual com uma variação do arpejo
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(mv.WORK / "cards" / f"{manual_id}.png"),
            "-vf", "scale=640:-1", "-q:v", "4", str(OUT / f"{manual_id}.jpg"),
        ],
        check=True,
    )
    size = video.stat().st_size / 1_048_576
    print(f"{manual_id}: {total:.0f}s, {size:.1f} MB")
    return {"id": manual_id, "title": title, "description": desc, "seconds": round(total)}


def main() -> None:
    only = set(sys.argv[1:])
    index_path = OUT / "manuais.json"
    index = {m["id"]: m for m in json.loads(index_path.read_text())} if index_path.exists() else {}
    for n, manual in enumerate(MANUAIS, 1):
        if only and manual[0] not in only:
            continue
        index[manual[0]] = build(n, manual)
    ordered = [index[m[0]] for m in MANUAIS if m[0] in index]
    index_path.write_text(json.dumps(ordered, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
