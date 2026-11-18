import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { Subscription } from 'rxjs';

import { fileIcon, formatSize } from './documents.models';
import { DocumentsService } from './documents.service';

export interface MessageDocument {
  id: string;
  name: string;
  content_type: string;
  size: number;
}

/** Mídia de uma mensagem do WhatsApp: prévia de imagem, player de áudio/vídeo ou arquivo. */
@Component({
  selector: 'app-message-media',
  template: `
    @if (pending()) {
      <span class="media media--pending"
        ><span class="icon">hourglass_top</span> Guardando o arquivo…</span
      >
    } @else if (doc(); as d) {
      @if (kind() === 'image' && url()) {
        <button type="button" class="media__thumb" (click)="open()" [attr.aria-label]="d.name">
          <img [src]="url()" [alt]="d.name" />
        </button>
      } @else if (kind() === 'audio' && url()) {
        <audio controls preload="metadata" [src]="url()"></audio>
      } @else if (kind() === 'video' && url()) {
        <video controls preload="metadata" [src]="url()"></video>
      } @else {
        <button type="button" class="media media--file" (click)="open()">
          <span class="icon">{{ icon(d) }}</span>
          <span class="media__name">{{ d.name }}</span>
          <span class="media__size">{{ size(d) }}</span>
        </button>
      }
    } @else {
      <span class="media media--missing">[{{ label() }}]</span>
    }
  `,
  styles: `
    :host {
      display: block;
      margin-bottom: 4px;
    }
    .media {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.9rem;
    }
    .media--pending,
    .media--missing {
      opacity: 0.75;
      font-style: italic;
    }
    .media--file {
      border: 1px solid var(--mat-sys-outline-variant);
      background: var(--mat-sys-surface-container-low);
      border-radius: 8px;
      padding: 6px 10px;
      cursor: pointer;
      color: inherit;
      font: inherit;
      max-width: 100%;
    }
    .media__name {
      font-weight: 600;
      overflow-wrap: anywhere;
      text-align: left;
    }
    .media__size {
      opacity: 0.7;
      white-space: nowrap;
    }
    .media__thumb {
      padding: 0;
      border: 0;
      background: none;
      cursor: zoom-in;
      display: block;
    }
    img,
    video {
      display: block;
      max-width: min(280px, 100%);
      max-height: 280px;
      border-radius: 8px;
    }
    audio {
      max-width: 100%;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MessageMedia {
  private readonly api = inject(DocumentsService);

  readonly doc = input<MessageDocument | null>(null);
  readonly pending = input(false);
  readonly label = input('Arquivo');

  readonly url = signal<string | null>(null);
  readonly kind = signal<'image' | 'audio' | 'video' | 'file'>('file');

  /**
   * O polling da conversa entrega um objeto `doc` novo a cada poucos segundos, mesmo sem
   * mudança. Recarregar a cada vez trocava o `src` do player e cortava o áudio no meio:
   * só o id do arquivo dispara uma nova carga.
   */
  private readonly docId = computed(() => this.doc()?.id ?? null);
  private loading: Subscription | null = null;

  constructor() {
    inject(DestroyRef).onDestroy(() => {
      this.loading?.unsubscribe();
      this.revoke();
    });
    effect(() => {
      this.docId();
      untracked(() => this.prepare(this.doc()));
    });
  }

  icon(d: MessageDocument): string {
    return fileIcon(d.content_type);
  }

  size(d: MessageDocument): string {
    return formatSize(d.size);
  }

  open(): void {
    const d = this.doc();
    if (d) this.api.open({ id: d.id, name: d.name, can_preview: true });
  }

  private prepare(d: MessageDocument | null): void {
    // Carga anterior ainda em andamento não pode sobrescrever a atual (nem vazar o blob).
    this.loading?.unsubscribe();
    this.loading = null;
    this.revoke();
    if (!d) return;
    const type = d.content_type;
    const kind = type.startsWith('image/')
      ? 'image'
      : type.startsWith('audio/')
        ? 'audio'
        : type.startsWith('video/')
          ? 'video'
          : 'file';
    this.kind.set(kind);
    // Prévia na própria conversa só para mídia leve; o resto abre ao clicar.
    if (kind !== 'file' && d.size <= 8 * 1024 * 1024) {
      this.loading = this.api.objectUrl(d.id).subscribe({ next: (url) => this.url.set(url) });
    } else if (kind !== 'file') {
      this.kind.set('file');
    }
  }

  private revoke(): void {
    const current = this.url();
    if (current) URL.revokeObjectURL(current);
    this.url.set(null);
  }
}
