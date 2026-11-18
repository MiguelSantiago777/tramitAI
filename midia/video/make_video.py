"""Monta o vídeo de apresentação: cartelas, telas reais, voz neural (edge-tts) e legendas.

Uso (no container do vídeo, depois do capture.py): python3 make_video.py [voz]
Saída: out/tramitai-apresentacao.mp4 (1920x1080, 30 fps) e out/roteiro.srt
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import edge_tts
from playwright.sync_api import sync_playwright

VOICE = sys.argv[1] if len(sys.argv) > 1 else "pt-BR-FranciscaNeural"
RATE = "+6%"
WORK, OUT, SHOTS = Path("work"), Path("out"), Path("work/shots")
for d in (WORK / "audio", WORK / "cards", WORK / "scenes", OUT):
    d.mkdir(parents=True, exist_ok=True)

# (id, imagem, rótulo no canto, foco do zoom (x, y em 0-1), narração)
SCENES = [
    (
        "abertura",
        "card:abertura",
        "",
        (0.5, 0.5),
        "Oi! Eu sou a Lia, a assistente virtual do TramitAI. Em poucos minutos, vou te mostrar "
        "como o seu escritório pode atender pelo WhatsApp com a minha ajuda, sem perder o "
        "controle de nada.",
    ),
    (
        "inicio",
        "inicio",
        "Tela inicial",
        (0.5, 0.3),
        "Esta é a tela inicial. Logo de cara, você vê o que precisa da sua atenção hoje: "
        "mensagens esperando aprovação, conversas não lidas, compromissos e tarefas do dia.",
    ),
    (
        "conversa",
        "conversa",
        "Triagem no WhatsApp",
        (0.75, 0.45),
        "Quando alguém novo chama o escritório no WhatsApp, eu envio o termo de uso de "
        "inteligência artificial. Depois do aceite, faço a triagem: pergunto o nome e entendo "
        "o que aconteceu, uma pergunta de cada vez. Eu nunca dou orientação jurídica. E se a "
        "mensagem chega fora do horário, eu aviso quando o escritório atende e já vou "
        "adiantando o atendimento.",
    ),
    (
        "agenda",
        "agenda",
        "Agenda da Lia",
        (0.55, 0.3),
        "Quando a triagem termina, eu ofereço horários livres da agenda do advogado. A pessoa "
        "escolhe, e o horário aparece aqui como a confirmar. Com um clique em Confirmar, o "
        "cliente recebe a confirmação no WhatsApp. E na véspera, eu lembro ele da consulta.",
    ),
    (
        "aprovacoes",
        "aprovacoes",
        "Você aprova",
        (0.5, 0.35),
        "Para quem já é cliente, eu escrevo a resposta e ela vem para esta fila. O advogado "
        "lê, ajusta se quiser e aprova. Nada sai para o cliente sem o seu ok.",
    ),
    (
        "ficha",
        "ficha",
        "Ficha do cliente",
        (0.55, 0.5),
        "Eu também acompanho os processos direto no tribunal. Quando há uma movimentação, "
        "explico em português simples para o cliente, sempre com a sua aprovação. Na ficha do "
        "cliente fica tudo junto: histórico, processos, honorários e documentos. E o que o "
        "cliente manda pelo WhatsApp já cai na pasta dele.",
    ),
    (
        "funil",
        "funil",
        "Funil de clientes",
        (0.5, 0.4),
        "Todo contato novo entra no funil, da primeira mensagem até o contrato fechado. Assim, "
        "você não perde nenhuma oportunidade.",
    ),
    (
        "financeiro",
        "financeiro",
        "Financeiro",
        (0.55, 0.35),
        "No financeiro, você cadastra os honorários em parcelas, gera Pix ou link de pagamento "
        "do Mercado Pago e envia a cobrança pelo WhatsApp. Quando o cliente paga, a parcela "
        "recebe baixa sozinha.",
    ),
    (
        "relatorios",
        "relatorios",
        "Relatórios",
        (0.5, 0.35),
        "Nos relatórios, você acompanha quantos contatos chegaram, quantos contrataram, como "
        "está o atendimento e quanto o escritório recebeu.",
    ),
    (
        "configuracoes",
        "configuracoes",
        "Você no controle",
        (0.45, 0.5),
        "E tudo isso você controla nas configurações: o horário de atendimento, se eu posso "
        "fazer a triagem sozinha e se posso oferecer horários na agenda.",
    ),
    (
        "fim",
        "card:fim",
        "",
        (0.5, 0.5),
        "Pronto! Esse é o TramitAI. Você pode testar grátis por catorze dias, em app ponto "
        "tramitai ponto pro. Qualquer dúvida, é só chamar a gente. Até mais!",
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


async def speak(scene_id: str, text: str) -> list[tuple[float, float, str]]:
    """Gera o áudio e devolve as palavras com tempo (início, fim, palavra) em segundos."""
    try:  # versões novas: tempo por palavra precisa ser pedido
        communicate = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    except TypeError:
        communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    words: list[tuple[float, float, str]] = []
    with open(WORK / "audio" / f"{scene_id}.mp3", "wb") as audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10_000_000
                words.append((start, start + chunk["duration"] / 10_000_000, chunk["text"]))
    return words


def with_punctuation(
    words: list[tuple[float, float, str]], text: str
) -> list[tuple[float, float, str]]:
    """A voz devolve as palavras sem pontuação: recupera a grafia do roteiro, em ordem."""
    tokens = text.split()
    out, j = [], 0
    for start, end, word in words:
        key = word.strip(".,!?:;").lower()
        for k in range(j, min(j + 3, len(tokens))):
            if tokens[k].strip(".,!?:;").lower() == key:
                out.append((start, end, tokens[k]))
                j = k + 1
                break
        else:
            out.append((start, end, word))
    return out


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


def ts(seconds: float, ass: bool = True) -> str:
    h, rem = divmod(max(seconds, 0), 3600)
    m, s = divmod(rem, 60)
    if ass:
        return f"{int(h)}:{int(m):02d}:{s:05.2f}"
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Noto Sans,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&HB0201A33,1,0,0,0,100,100,0,0,3,18,0,2,200,200,64,1
Style: Label,Noto Sans,34,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00E54649,1,0,0,0,100,100,0,0,3,14,0,9,48,48,44,1

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


def render_scene(index: int, scene: tuple, words: list) -> tuple[Path, float, list]:
    scene_id, image, label, (fx, fy), _ = scene
    audio = WORK / "audio" / f"{scene_id}.mp3"
    pad_before, pad_after = 0.35, 0.9
    total = pad_before + duration(audio) + pad_after
    caps = [
        (s + pad_before, e + pad_before, t)
        for s, e, t in captions(with_punctuation(words, scene[4]))
    ]

    ass = WORK / "scenes" / f"{scene_id}.ass"
    events = [f"Dialogue: 0,{ts(s)},{ts(e)},Cap,,0,0,0,,{t}" for s, e, t in caps]
    if label:
        events.append(f"Dialogue: 1,{ts(0)},{ts(total)},Label,,0,0,0,,{label}")
    ass.write_text(ASS_HEADER + "\n".join(events) + "\n", encoding="utf-8")

    src = WORK / "cards" / f"{image[5:]}.png" if image.startswith("card:") else SHOTS / f"{image}.png"
    frames = int(total * 30)
    zoom_to = 1.0 if image.startswith("card:") else 1.08
    vf = (
        "scale=3840:2160,"
        f"zoompan=z='1+({zoom_to}-1)*on/{frames}':"
        f"x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':d={frames}:s=1920x1080:fps=30,"
        f"subtitles={ass}:fontsdir=/usr/share/fonts,"
        f"fade=t=in:st=0:d=0.35,fade=t=out:st={total - 0.35:.2f}:d=0.35"
    )
    out = WORK / "scenes" / f"{index:02d}-{scene_id}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(src),
            "-i", str(audio),
            "-filter_complex",
            f"[0:v]{vf}[v];[1:a]adelay={int(pad_before * 1000)}:all=1,apad[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            str(out),
        ],
        check=True,
    )
    return out, total, caps


def main() -> None:
    render_cards()
    timings = {s[0]: asyncio.run(speak(s[0], s[4])) for s in SCENES}
    parts, srt, offset, n = [], [], 0.0, 1
    for i, scene in enumerate(SCENES):
        path, total, caps = render_scene(i, scene, timings[scene[0]])
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
