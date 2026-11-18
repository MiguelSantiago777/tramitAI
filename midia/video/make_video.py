"""Monta o vídeo de apresentação: cartelas, telas reais, voz neural (edge-tts) e legendas.

Quando a Lia cita uma parte do sistema, o elemento é circulado e sublinhado na tela no
momento da fala, e o termo aparece destacado na legenda.

Uso (no container do vídeo, depois do capture.py): python3 make_video.py [voz]
Saída: out/tramitai-apresentacao.mp4 (1920x1080, 30 fps) e out/roteiro.srt
"""

import asyncio
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import edge_tts
from playwright.sync_api import sync_playwright

VOICE = sys.argv[1] if len(sys.argv) > 1 else "pt-BR-FranciscaNeural"
RATE = "+6%"
WORK, OUT, SHOTS = Path("work"), Path("out"), Path("work/shots")
for d in (WORK / "audio", WORK / "cards", WORK / "scenes", OUT):
    d.mkdir(parents=True, exist_ok=True)

# Como a voz deve falar (a legenda continua com a grafia certa): "Tra-mi-TAI".
SPOKEN = {"TramitAI": "Tramitái"}
HIGHLIGHT = "&H3DC8FF&"  # âmbar (#FFC83D) em BGR do ASS

# id, imagem, rótulo no canto, narração, destaques [(trecho da fala, alvo na tela)]
SCENES = [
    (
        "abertura",
        "card:abertura",
        "",
        "Oi! Eu sou a Lia, a assistente virtual do TramitAI. Em poucos minutos, vou te mostrar "
        "como o seu escritório pode atender pelo WhatsApp com a minha ajuda, sem perder o "
        "controle de nada.",
        [],
    ),
    (
        "inicio",
        "inicio",
        "Tela inicial",
        "Esta é a tela inicial. Logo de cara, você vê o que precisa da sua atenção hoje: "
        "mensagens esperando aprovação, conversas não lidas, compromissos e tarefas do dia.",
        [("mensagens esperando aprovação", "resumo"), ("compromissos e tarefas do dia", "mesa")],
    ),
    (
        "conversa",
        "conversa",
        "Triagem no WhatsApp",
        "Quando alguém novo chama o escritório no WhatsApp, eu envio o termo de uso de "
        "inteligência artificial. Depois do aceite, faço a triagem: pergunto o nome e entendo "
        "o que aconteceu, uma pergunta de cada vez. Eu nunca dou orientação jurídica. E se a "
        "mensagem chega fora do horário, eu aviso quando o escritório atende e já vou "
        "adiantando o atendimento.",
        [("faço a triagem", "triagem"), ("fora do horário", "aviso_horario")],
    ),
    (
        "agenda",
        "agenda",
        "Agenda da Lia",
        "Quando a triagem termina, eu ofereço horários livres da agenda do advogado. A pessoa "
        "escolhe, e o horário aparece aqui como a confirmar. Com um clique em Confirmar, o "
        "cliente recebe a confirmação no WhatsApp. E na véspera, eu lembro ele da consulta.",
        [("a confirmar", "pendentes"), ("clique em Confirmar", "confirmar")],
    ),
    (
        "aprovacoes",
        "aprovacoes",
        "Você aprova",
        "Para quem já é cliente, eu escrevo a resposta e ela vem para esta fila de aprovação. "
        "O advogado lê, ajusta se quiser e aprova. Nada sai para o cliente sem o seu ok.",
        [("fila de aprovação", "rascunho"), ("aprova", "aprovar")],
    ),
    (
        "ficha",
        "ficha",
        "Ficha do cliente",
        "Eu também acompanho os processos direto no tribunal. Quando há uma movimentação, "
        "explico em português simples para o cliente, sempre com a sua aprovação. Na ficha do "
        "cliente fica tudo junto: histórico, processos, honorários e documentos. E o que o "
        "cliente manda pelo WhatsApp já cai na pasta dele.",
        [
            ("histórico", "historico"),
            ("honorários", "honorarios"),
            ("documentos", "documentos"),
        ],
    ),
    (
        "funil",
        "funil",
        "Funil de clientes",
        "Todo contato novo entra no funil, da primeira mensagem até o contrato fechado. Assim, "
        "você não perde nenhuma oportunidade.",
        [("funil", "quadro"), ("contrato fechado", "contratou")],
    ),
    (
        "financeiro",
        "financeiro",
        "Financeiro",
        "No financeiro, você cadastra os honorários em parcelas, gera Pix ou link de pagamento "
        "do Mercado Pago e envia a cobrança pelo WhatsApp. Quando o cliente paga, a parcela "
        "recebe baixa sozinha.",
        [("parcelas", "parcelas"), ("gera Pix", "pix"), ("baixa sozinha", "recebido")],
    ),
    (
        "relatorios",
        "relatorios",
        "Relatórios",
        "Nos relatórios, você acompanha quantos contatos chegaram, quantos contrataram, como "
        "está o atendimento e quanto o escritório recebeu.",
        [("quantos contatos chegaram", "contatos"), ("quanto o escritório recebeu", "recebido")],
    ),
    (
        "configuracoes",
        "configuracoes",
        "Você no controle",
        "E tudo isso você controla nas configurações: se eu posso fazer a triagem sozinha, o "
        "horário de atendimento e se posso oferecer horários na agenda.",
        [
            ("triagem sozinha", "triagem"),
            ("horário de atendimento", "horario"),
            ("oferecer horários na agenda", "agenda"),
        ],
    ),
    (
        "fim",
        "card:fim",
        "",
        "Pronto! Esse é o TramitAI. Você pode testar grátis por catorze dias, em app ponto "
        "tramitai ponto pro. Qualquer dúvida, é só chamar a gente. Até mais!",
        [],
    ),
]

CARD_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;width:1920px;height:1080px;font-family:'Noto Sans',sans-serif;color:#fff;
background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 55%,#0e7490 100%)}
.wrap{height:100%;display:flex;flex-direction:column;justify-content:center;padding:0 180px}
.logo{display:flex;align-items:center;gap:24px;font-size:64px;font-weight:700}
.mark{width:96px;height:96px;border-radius:24px;background:#fff;color:#4f46e5;display:grid;
place-items:center;font-size:60px;font-weight:800}
h1{font-size:84px;line-height:1.1;margin:56px 0 24px;max-width:1300px}
p{font-size:40px;margin:0;opacity:.9;max-width:1300px;line-height:1.4}
.pill{align-self:flex-start;margin-top:48px;padding:18px 36px;border-radius:999px;
background:#fff;color:#4f46e5;font-size:44px;font-weight:700}
</style></head><body><div class="wrap">
<div class="logo"><span class="mark">T</span>TramitAI</div>{body}</div></body></html>"""

CARDS = {
    "abertura": "<h1>A secretária jurídica do seu escritório no WhatsApp</h1>"
    "<p>Triagem, agenda, processos e honorários, com o advogado sempre no controle.</p>",
    "fim": "<h1>Teste grátis por 14 dias</h1><p>Sem cartão para começar.</p>"
    '<span class="pill">app.tramitai.pro</span>',
}


def render_cards() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        for name, body in CARDS.items():
            page.set_content(CARD_HTML.replace("{body}", body))
            page.screenshot(path=str(WORK / "cards" / f"{name}.png"))
        browser.close()


def spoken(text: str) -> str:
    for written, said in SPOKEN.items():
        text = text.replace(written, said)
    return text


async def speak(scene_id: str, text: str) -> list[tuple[float, float, str]]:
    """Gera o áudio e devolve as palavras com tempo (início, fim, palavra) em segundos."""
    try:  # versões novas: tempo por palavra precisa ser pedido
        communicate = edge_tts.Communicate(
            spoken(text), VOICE, rate=RATE, boundary="WordBoundary"
        )
    except TypeError:
        communicate = edge_tts.Communicate(spoken(text), VOICE, rate=RATE)
    words: list[tuple[float, float, str]] = []
    with open(WORK / "audio" / f"{scene_id}.mp3", "wb") as audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10_000_000
                words.append((start, start + chunk["duration"] / 10_000_000, chunk["text"]))
    return words


def norm(word: str) -> str:
    plain = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in plain if c.isalnum())


def with_written_words(
    words: list[tuple[float, float, str]], text: str
) -> list[tuple[float, float, str]]:
    """A voz devolve as palavras sem pontuação e na pronúncia: recupera a grafia do roteiro."""
    tokens, said = text.split(), spoken(text).split()
    out, j = [], 0
    for start, end, word in words:
        for k in range(j, min(j + 3, len(said))):
            if norm(said[k]) == norm(word):
                out.append((start, end, tokens[k]))
                j = k + 1
                break
        else:
            out.append((start, end, word))
    return out


def phrase_time(words: list[tuple[float, float, str]], phrase: str) -> float | None:
    """Momento em que a Lia começa a falar o trecho."""
    target = [norm(w) for w in phrase.split()]
    keys = [norm(w[2]) for w in words]
    for i in range(len(keys) - len(target) + 1):
        if keys[i : i + len(target)] == target:
            return words[i][0]
    return None


def captions(words: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Agrupa as palavras em legendas curtas (até ~42 caracteres, quebra em pontuação)."""
    lines, current, start = [], [], 0.0
    for i, (w_start, w_end, word) in enumerate(words):
        if not current:
            start = w_start
        current.append(word)
        text = " ".join(current)
        last = i == len(words) - 1
        sentence_end = word.endswith((".", "!", "?"))
        pause = word.endswith((",", ":")) and len(text) > 18
        if last or len(text) >= 42 or sentence_end or pause:
            end = w_end if last else max(w_end, words[i + 1][0] - 0.05)
            lines.append((start, end, text))
            current = []
    return lines


def mark_terms(text: str, phrases: list[str]) -> str:
    """Termos do sistema em destaque na legenda: âmbar e sublinhado."""
    for phrase in sorted(phrases, key=len, reverse=True):
        text = re.sub(
            rf"(?<![\w{{]){re.escape(phrase)}(?!\w)",
            lambda m: f"{{\\c{HIGHLIGHT}\\u1}}{m.group(0)}{{\\c&HFFFFFF&\\u0}}",
            text,
            flags=re.IGNORECASE,
        )
    return text


def ts(seconds: float, ass: bool = True) -> str:
    h, rem = divmod(max(seconds, 0), 3600)
    m, s = divmod(rem, 60)
    if ass:
        return f"{int(h)}:{int(m):02d}:{s:05.2f}"
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def highlight_events(box: list[int], start: float, end: float) -> list[str]:
    """Moldura âmbar em volta do elemento + sublinhado que se "desenha" da esquerda pra direita."""
    pad = 10
    x1, y1, x2, y2 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
    x1, y1, x2, y2 = max(x1, 4), max(y1, 4), min(x2, 1916), min(y2, 1066)
    rect = f"m {x1} {y1} l {x2} {y1} l {x2} {y2} l {x1} {y2}"
    under_y1, under_y2 = min(y2 + 6, 1068), min(y2 + 16, 1076)
    bar = f"m {x1} {under_y1} l {x2} {under_y1} l {x2} {under_y2} l {x1} {under_y2}"
    common = r"\an7\pos(0,0)\shad0"
    t0, t1 = ts(start), ts(end)
    return [
        # leve preenchimento para "acender" a área
        f"Dialogue: 2,{t0},{t1},Draw,,0,0,0,,{{{common}\\bord0\\1c{HIGHLIGHT}\\1a&HD8&"
        f"\\fad(250,250)\\p1}}{rect}{{\\p0}}",
        # contorno
        f"Dialogue: 3,{t0},{t1},Draw,,0,0,0,,{{{common}\\bord5\\3c{HIGHLIGHT}\\1a&HFF&"
        f"\\fad(250,250)\\p1}}{rect}{{\\p0}}",
        # sublinhado varrendo
        f"Dialogue: 4,{t0},{t1},Draw,,0,0,0,,{{{common}\\bord0\\1c{HIGHLIGHT}\\fad(150,250)"
        f"\\clip({x1},0,{x1},1080)\\t(0,450,\\clip({x1},0,{x2},1080))\\p1}}{bar}{{\\p0}}",
    ]


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Noto Sans,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H20201A33,1,0,0,0,100,100,0,0,3,18,0,2,200,200,64,1
Style: Label,Noto Sans,34,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00E54649,1,0,0,0,100,100,0,0,3,14,0,9,48,48,44,1
Style: Draw,Noto Sans,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def render_scene(index: int, scene: tuple, raw_words: list, boxes: dict) -> tuple[Path, float, list]:
    scene_id, image, label, text, highlights = scene
    audio = WORK / "audio" / f"{scene_id}.mp3"
    pad_before, pad_after = 0.35, 0.9
    total = pad_before + duration(audio) + pad_after
    words = with_written_words(raw_words, text)
    caps = [(s + pad_before, e + pad_before, t) for s, e, t in captions(words)]
    terms = [phrase for phrase, _ in highlights]

    events = [
        f"Dialogue: 5,{ts(s)},{ts(e)},Cap,,0,0,0,,{mark_terms(t, terms)}" for s, e, t in caps
    ]
    if label:
        events.append(f"Dialogue: 6,{ts(0)},{ts(total)},Label,,0,0,0,,{label}")
    # Cada destaque fica até o próximo começar (ou até o fim da cena).
    timed = []
    for phrase, target in highlights:
        when = phrase_time(words, phrase)
        target_box = boxes.get(image, {}).get(target)
        if when is None or target_box is None:
            print(f"  aviso: destaque '{phrase}' ({target}) não encaixou")
            continue
        timed.append((when + pad_before, target_box))
    timed.sort()
    for i, (start, target_box) in enumerate(timed):
        end = timed[i + 1][0] if i + 1 < len(timed) else total - 0.2
        events.extend(highlight_events(target_box, start, end))

    ass = WORK / "scenes" / f"{scene_id}.ass"
    ass.write_text(ASS_HEADER + "\n".join(events) + "\n", encoding="utf-8")

    src = WORK / "cards" / f"{image[5:]}.png" if image.startswith("card:") else SHOTS / f"{image}.png"
    # Imagem parada (sem zoom: o zoom do ffmpeg arredonda a posição e faz a tela tremer).
    vf = (
        "scale=1920:1080:flags=lanczos,format=yuv420p,"
        f"subtitles={ass}:fontsdir=/usr/share/fonts,"
        f"fade=t=in:st=0:d=0.35,fade=t=out:st={total - 0.35:.2f}:d=0.35"
    )
    out = WORK / "scenes" / f"{index:02d}-{scene_id}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-framerate", "30", "-i", str(src),
            "-i", str(audio),
            "-filter_complex",
            f"[0:v]{vf}[v];[1:a]adelay={int(pad_before * 1000)}:all=1,apad[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            str(out),
        ],
        check=True,
    )
    return out, total, caps


def main() -> None:
    render_cards()
    boxes = json.loads((SHOTS / "boxes.json").read_text(encoding="utf-8"))
    timings = {s[0]: asyncio.run(speak(s[0], s[3])) for s in SCENES}
    parts, srt, offset, n = [], [], 0.0, 1
    for i, scene in enumerate(SCENES):
        path, total, caps = render_scene(i, scene, timings[scene[0]], boxes)
        parts.append(path)
        for s, e, t in caps:
            srt.append(f"{n}\n{ts(offset + s, False)} --> {ts(offset + e, False)}\n{t}\n")
            n += 1
        offset += total
        print(f"cena {scene[0]}: {total:.1f}s")
    listing = WORK / "scenes" / "lista.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(listing), "-c", "copy", "-movflags", "+faststart",
            str(OUT / "tramitai-apresentacao.mp4"),
        ],
        check=True,
    )
    (OUT / "roteiro.srt").write_text("\n".join(srt), encoding="utf-8")
    print(f"pronto: out/tramitai-apresentacao.mp4 ({offset:.0f}s)")


if __name__ == "__main__":
    main()
