import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink } from '@angular/router';

import { Publication } from './publication.models';
import { PublicationsService } from './publications.service';

/** Publicações do Diário deste processo (some se não houver ou se o plano não inclui). */
@Component({
  selector: 'app-case-publications',
  imports: [DatePipe, RouterLink, MatButtonModule],
  template: `
    @if (items().length > 0) {
      <section class="card box" aria-labelledby="case-pubs-title">
        <header class="box__head">
          <h2 id="case-pubs-title">Publicações no Diário</h2>
          <span class="spacer"></span>
          <a mat-button routerLink="/publicacoes">Ver todas</a>
        </header>
        @for (p of items(); track p.id) {
          <details class="pub" [attr.data-status]="p.status">
            <summary>
              <span class="pub__date">{{ p.available_on | date: 'dd/MM/yyyy' }}</span>
              <strong>{{ p.kind || 'Publicação' }}</strong>
              @if (p.document_type) {
                <span class="muted"> · {{ p.document_type }}</span>
              }
              @if (p.status === 'NEW') {
                <span class="badge" data-status="NEWS">nova</span>
              }
              @if (p.deadline_hints.length > 0) {
                <span class="muted small">
                  · menciona prazo de {{ p.deadline_hints.join(', ') }}</span
                >
              }
            </summary>
            <p class="muted small">{{ p.orgao }}</p>
            <p class="pub__text">{{ p.text }}</p>
            @if (p.link) {
              <a mat-button [href]="p.link" target="_blank" rel="noopener noreferrer"
                >Ver no tribunal</a
              >
            }
          </details>
        }
        @if (total() > items().length) {
          <p class="muted small">
            Mostrando as {{ items().length }} mais recentes de {{ total() }}.
          </p>
        }
      </section>
    }
  `,
  styles: `
    .box {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-top: 16px;
      padding: 20px 24px;
    }
    .box__head {
      display: flex;
      align-items: center;
    }
    h2 {
      margin: 0;
      font: var(--mat-sys-title-medium);
    }
    .spacer {
      flex: 1;
    }
    .pub {
      padding: 8px 12px;
      border-left: 3px solid var(--mat-sys-primary);
    }
    .pub[data-status='DONE'],
    .pub[data-status='IGNORED'] {
      border-left-color: var(--mat-sys-outline-variant);
    }
    summary {
      cursor: pointer;
    }
    .pub__date {
      margin-right: 8px;
      font-variant-numeric: tabular-nums;
    }
    .pub__text {
      white-space: pre-line;
      overflow-wrap: anywhere;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CasePublications {
  private readonly api = inject(PublicationsService);

  readonly caseId = input.required<string>();
  readonly items = signal<Publication[]>([]);
  readonly total = signal(0);

  constructor() {
    effect(() => {
      const id = this.caseId();
      untracked(() =>
        this.api.list({ case_id: id }, 0, 10).subscribe({
          next: (page) => {
            this.items.set(page.results);
            this.total.set(page.count);
          },
          // Plano sem publicações (402) ou falha: o painel só não aparece.
          error: () => this.items.set([]),
        }),
      );
    });
  }
}
