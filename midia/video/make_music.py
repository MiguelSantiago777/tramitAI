"""Trilha de fundo dos vídeos, composta aqui mesmo (sem direitos autorais de terceiros).

Pad suave + baixo + arpejo de "piano" em Dó maior (Cmaj7, Am7, Fmaj7, G6), 80 bpm, com reverb.
Uso: python3 make_music.py <segundos> <saida.wav>   (ou importado: make_music.render(...))
"""

import sys
import wave
from pathlib import Path

import numpy as np

RATE = 44100
BPM = 80
BEAT = 60 / BPM
BAR = 4 * BEAT
# (fundamental do baixo, notas do acorde) em MIDI
CHORDS = [
    (36, [60, 64, 67, 71]),  # Cmaj7
    (33, [57, 60, 64, 67]),  # Am7
    (29, [53, 57, 60, 64]),  # Fmaj7
    (31, [55, 59, 62, 64]),  # G6
]


def hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def envelope(n: int, attack: float, release: float) -> np.ndarray:
    env = np.ones(n)
    a, r = int(attack * RATE), int(release * RATE)
    env[:a] = np.linspace(0, 1, a)
    env[n - r :] *= np.linspace(1, 0, r)
    return env


def pad(chord: list[int], seconds: float) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for note in chord:
        for detune in (-0.06, 0.06):
            f = hz(note + detune)
            out += np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)
    # Leve "respiração" para não soar parado.
    out *= 0.85 + 0.15 * np.sin(2 * np.pi * 0.25 * t)
    return out / (len(chord) * 2) * envelope(n, 0.9, 1.2)


def pluck(note: int, seconds: float, velocity: float) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    f = hz(note)
    tone = (
        np.sin(2 * np.pi * f * t)
        + 0.35 * np.sin(4 * np.pi * f * t) * np.exp(-t * 6)
        + 0.12 * np.sin(6 * np.pi * f * t) * np.exp(-t * 9)
    )
    return velocity * tone * np.exp(-t * 2.8) * envelope(n, 0.004, 0.05)


def bass(note: int, seconds: float) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    f = hz(note)
    return (np.sin(2 * np.pi * f * t) + 0.2 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 0.9) * (
        envelope(n, 0.02, 0.4)
    )


def reverb(signal: np.ndarray, seconds: float = 2.2, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    impulse = rng.standard_normal(n) * np.exp(-t * 3.2)
    impulse[0] = 0
    size = 1 << int(np.ceil(np.log2(len(signal) + n)))
    wet = np.fft.irfft(np.fft.rfft(signal, size) * np.fft.rfft(impulse, size), size)
    wet = wet[: len(signal)]
    return wet / (np.max(np.abs(wet)) + 1e-9)


def render(seconds: float, path: Path, seed: int = 1) -> Path:
    rng = np.random.default_rng(seed)
    total = int((seconds + 3) * RATE)
    left, right = np.zeros(total), np.zeros(total)

    def put(buf: np.ndarray, start: float, sound: np.ndarray, gain: float) -> None:
        i = int(start * RATE)
        if i >= total:
            return
        end = min(total, i + len(sound))
        buf[i:end] += gain * sound[: end - i]

    # Arpejo em colcheias, padrão que varia um pouco a cada volta.
    patterns = [[0, 1, 2, 3, 2, 1, 2, 3], [0, 2, 1, 3, 2, 3, 1, 2], [0, 1, 3, 2, 3, 1, 2, 1]]
    bar, start = 0, 0.0
    while start < seconds + 1:
        root, chord = CHORDS[bar % len(CHORDS)]
        chord_pad = pad(chord, BAR + 1.4)
        put(left, start, chord_pad, 0.55)
        put(right, start, chord_pad, 0.55)
        low = bass(root, BAR + 0.4)
        put(left, start, low, 0.45)
        put(right, start, low, 0.45)
        if bar >= 1:  # primeiro compasso só o pad: entrada mais suave
            pattern = patterns[(bar // len(CHORDS)) % len(patterns)]
            for step, index in enumerate(pattern):
                note = chord[index] + 12
                velocity = 0.28 + 0.08 * rng.random()
                tone = pluck(note, 1.6, velocity)
                pan = 0.35 + 0.3 * (step % 2)
                when = start + step * BEAT / 2 + rng.normal(0, 0.006)
                put(left, max(0, when), tone, 1 - pan)
                put(right, max(0, when), tone, pan)
        bar += 1
        start += BAR

    mix = []
    for dry in (left, right):
        wet = reverb(dry, seed=seed + len(mix))
        mix.append(0.75 * dry / (np.max(np.abs(dry)) + 1e-9) + 0.35 * wet)
    stereo = np.stack(mix, axis=1)[: int(seconds * RATE)]
    # Entrada e saída suaves.
    n = len(stereo)
    fade_in, fade_out = int(1.5 * RATE), int(min(3.0, seconds / 4) * RATE)
    stereo[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    stereo[n - fade_out :] *= np.linspace(1, 0, fade_out)[:, None]
    stereo *= 0.89 / (np.max(np.abs(stereo)) + 1e-9)

    pcm = (stereo * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return path


if __name__ == "__main__":
    render(float(sys.argv[1]), Path(sys.argv[2]))
