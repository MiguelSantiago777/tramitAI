import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSnackBar } from '@angular/material/snack-bar';

import { AuthService } from '../../../core/auth/auth.service';
import { toApiError } from '../../../core/http/api-error';
import { DraftCard } from '../draft-card/draft-card';
import { Draft, DraftStatus } from '../draft.models';
import { DraftsService } from '../drafts.service';
import { PendingDraftsCounter } from '../pending-counter';

@Component({
  selector: 'app-approvals',
  imports: [
    ReactiveFormsModule,
    MatButtonToggleModule,
    MatPaginatorModule,
    MatProgressBarModule,
    DraftCard,
  ],
  template: `
    <header class="page-header">
      <div>
        <h1>Aprovações</h1>
        <p>Nada sai para o cliente sem a sua aprovação. Revise, edite se precisar e aprove.</p>
      </div>
    </header>

    <mat-button-toggle-group [formControl]="status" aria-label="Situação" class="approvals__tabs">
      <mat-button-toggle value="DRAFT">Pendentes</mat-button-toggle>
      <mat-button-toggle value="AWAITING">Aguardando cliente</mat-button-toggle>
      <mat-button-toggle value="SENT">Enviadas</mat-button-toggle>
      <mat-button-toggle value="REJECTED">Rejeitadas</mat-button-toggle>
      <mat-button-toggle value="FAILED">Com falha</mat-button-toggle>
    </mat-button-toggle-group>

    @if (loading()) {
      <mat-progress-bar mode="indeterminate" />
    }
    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    <div class="approvals__list">
      @for (d of drafts(); track d.id) {
        <app-draft-card [draft]="d" [canDecide]="canDecide()" (decided)="onDecided($event)" />
      } @empty {
        @if (!loading()) {
          <div class="card empty-state">
            <span class="icon">inbox</span>
            {{
              status.value === 'DRAFT'
                ? 'Tudo em dia. Nenhuma mensagem esperando aprovação.'
                : 'Nada por aqui.'
            }}
          </div>
        }
      }
    </div>

    @if (total() > pageSize) {
      <mat-paginator
        [length]="total()"
        [pageIndex]="pageIndex()"
        [pageSize]="pageSize"
        [hidePageSize]="true"
        (page)="onPage($event)"
      />
    }
  `,
  styles: `
    .approvals__tabs {
      margin-bottom: 16px;
      flex-wrap: wrap;
    }
    .approvals__list {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Approvals {
  private readonly api = inject(DraftsService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly counter = inject(PendingDraftsCounter);
  private readonly auth = inject(AuthService);

  readonly pageSize = 25;
  readonly status = new FormControl<DraftStatus>('DRAFT', { nonNullable: true });
  readonly drafts = signal<Draft[]>([]);
  readonly total = signal(0);
  readonly pageIndex = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly canDecide = computed(() => this.auth.session()?.can_approve ?? false);

  constructor() {
    this.status.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => {
      this.pageIndex.set(0);
      this.load();
    });
    this.load();
  }

  onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.load();
  }

  onDecided(updated: Draft): void {
    this.snackBar.open(decisionMessage(updated), undefined, { duration: 4000 });
    if (this.status.value === 'DRAFT') {
      this.drafts.update((list) => list.filter((d) => d.id !== updated.id));
      this.total.update((n) => Math.max(0, n - 1));
    }
    this.counter.refresh();
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.list({ status: this.status.value }, this.pageIndex(), this.pageSize).subscribe({
      next: (page) => {
        this.drafts.set(page.results);
        this.total.set(page.count);
        this.loading.set(false);
      },
      error: (err: unknown) => {
        this.error.set(toApiError(err).message);
        this.loading.set(false);
      },
    });
  }
}

function decisionMessage(draft: Draft): string {
  switch (draft.status) {
    case 'AWAITING':
      return 'Aviso enviado pelo modelo da Meta. O texto sai quando o cliente responder.';
    case 'APPROVED':
    case 'SENT':
      return 'Mensagem aprovada e enviada.';
    default:
      return 'Rascunho rejeitado.';
  }
}
