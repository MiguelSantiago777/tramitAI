import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

export interface Manual {
  id: string;
  title: string;
  description: string;
  seconds: number;
}

/** Vídeos e capas ficam em public/videos/manuais (gerados por midia/video/make_manuais.py). */
export const MANUAIS_BASE = '/videos/manuais';

export function duration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m ? `${m}min${s ? ` ${String(s).padStart(2, '0')}s` : ''}` : `${s}s`;
}

/** Manuais em vídeo: a pessoa assiste quando quiser, direto no sistema. */
@Component({
  selector: 'app-manuais-page',
  template: `
    <header class="page-header">
      <div>
        <h1>Manuais</h1>
        <p>Vídeos curtos, com a Lia, mostrando como usar cada parte do sistema.</p>
      </div>
    </header>

    @if (error()) {
      <p class="error-text" role="alert">Não foi possível carregar os manuais agora.</p>
    }

    @if (current(); as m) {
      <section class="card panel-card player">
        <video
          [src]="video(m)"
          [poster]="poster(m)"
          controls
          preload="metadata"
          playsinline
          [attr.aria-label]="m.title"
        ></video>
        <div class="player__info">
          <h2 class="section-title">
            <span class="icon">play_circle</span> {{ position(m) }}. {{ m.title }}
          </h2>
          <p class="muted">{{ m.description }} · {{ length(m) }}</p>
          @if (next(); as n) {
            <button type="button" class="player__next" (click)="select(n)">
              Próximo: {{ n.title }} <span class="icon">arrow_forward</span>
            </button>
          }
        </div>
      </section>
    }

    <ol class="grid">
      @for (m of manuais(); track m.id; let i = $index) {
        <li>
          <button
            type="button"
            class="card item"
            [class.item--active]="m.id === current()?.id"
            (click)="select(m)"
          >
            <img [src]="poster(m)" [alt]="m.title" loading="lazy" />
            <span class="item__text">
              <strong>{{ i + 1 }}. {{ m.title }}</strong>
              <span class="muted small">{{ m.description }}</span>
              <span class="muted small item__time"
                ><span class="icon">schedule</span>{{ length(m) }}</span
              >
            </span>
          </button>
        </li>
      }
    </ol>
  `,
  styles: `
    .player {
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(220px, 1fr);
      gap: 20px;
      align-items: start;
      margin-top: 0;
    }
    video {
      width: 100%;
      aspect-ratio: 16 / 9;
      border-radius: var(--tm-radius-sm);
      background: #0f172a;
    }
    .player__info p {
      margin: 0 0 12px;
    }
    .player__next {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 0;
      border: 0;
      background: none;
      color: var(--mat-sys-primary);
      font:
        600 14px / 1.4 Inter,
        system-ui,
        sans-serif;
      cursor: pointer;
    }
    .grid {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 16px;
    }
    .item {
      width: 100%;
      padding: 0;
      overflow: hidden;
      text-align: left;
      font: inherit;
      color: inherit;
      cursor: pointer;
      transition:
        box-shadow 120ms ease,
        transform 120ms ease;
    }
    .item:hover {
      transform: translateY(-1px);
      box-shadow: var(--tm-shadow-lg);
    }
    .item--active {
      outline: 2px solid var(--mat-sys-primary);
      outline-offset: -2px;
    }
    .item img {
      display: block;
      width: 100%;
      aspect-ratio: 16 / 9;
      object-fit: cover;
    }
    .item__text {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 12px 14px 14px;
    }
    .item__time {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .item__time .icon {
      font-size: 16px;
    }
    @media (max-width: 900px) {
      .player {
        grid-template-columns: 1fr;
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ManuaisPage {
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly manuais = signal<Manual[]>([]);
  readonly selectedId = signal<string | null>(this.route.snapshot.queryParamMap.get('v'));
  readonly error = signal(false);

  readonly current = computed(() => {
    const list = this.manuais();
    return list.find((m) => m.id === this.selectedId()) ?? list[0] ?? null;
  });
  readonly next = computed(() => {
    const list = this.manuais();
    const index = list.findIndex((m) => m.id === this.current()?.id);
    return index >= 0 ? (list[index + 1] ?? null) : null;
  });

  constructor() {
    inject(HttpClient)
      .get<Manual[]>(`${MANUAIS_BASE}/manuais.json`)
      .subscribe({
        next: (list) => this.manuais.set(list),
        error: () => this.error.set(true),
      });
  }

  video(m: Manual): string {
    return `${MANUAIS_BASE}/${m.id}.mp4`;
  }

  poster(m: Manual): string {
    return `${MANUAIS_BASE}/${m.id}.jpg`;
  }

  length(m: Manual): string {
    return duration(m.seconds);
  }

  position(m: Manual): number {
    return this.manuais().findIndex((x) => x.id === m.id) + 1;
  }

  select(m: Manual): void {
    this.selectedId.set(m.id);
    void this.router.navigate([], { queryParams: { v: m.id }, replaceUrl: true });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}
