import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSnackBar } from '@angular/material/snack-bar';
import { RouterLink } from '@angular/router';

import { toApiError } from '../../../core/http/api-error';
import { CaseMovement, LegalCase, NOTIFICATION_LABELS, SYNC_STATUS_LABELS } from '../case.models';
import { CasesService } from '../cases.service';

const PAGE_SIZE = 20;

/** Andamentos do processo (DataJud) e o botão de consultar agora. */
@Component({
  selector: 'app-case-movements',
  imports: [DatePipe, RouterLink, MatButtonModule, MatProgressBarModule],
  templateUrl: './case-movements.html',
  styleUrl: './case-movements.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CaseMovements {
  private readonly cases = inject(CasesService);
  private readonly snackBar = inject(MatSnackBar);

  readonly legalCase = input.required<LegalCase>();
  /** Pede ao pai para recarregar o processo (status da consulta). */
  readonly refresh = output<void>();

  readonly movements = signal<CaseMovement[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly checking = signal(false);
  readonly error = signal<string | null>(null);
  private page = 0;

  readonly syncLabel = computed(() => SYNC_STATUS_LABELS[this.legalCase().sync_status]);
  readonly hasMore = computed(() => this.movements().length < this.total());
  readonly monitored = computed(
    () => this.legalCase().monitoring_enabled && this.legalCase().status === 'ACTIVE',
  );

  constructor() {
    effect(() => {
      const id = this.legalCase().id;
      untracked(() => this.load(id, 0));
    });
  }

  notificationLabel(m: CaseMovement): string {
    return NOTIFICATION_LABELS[m.notification];
  }

  more(): void {
    this.load(this.legalCase().id, this.page + 1);
  }

  checkNow(): void {
    this.checking.set(true);
    this.error.set(null);
    this.cases.check(this.legalCase().id).subscribe({
      next: () => {
        this.checking.set(false);
        this.snackBar.open('Consulta pedida. Os andamentos aparecem em instantes.', undefined, {
          duration: 4000,
        });
        // A consulta roda na fila; dá um tempo e recarrega.
        setTimeout(() => {
          this.refresh.emit();
          this.load(this.legalCase().id, 0);
        }, 5000);
      },
      error: (err: unknown) => {
        this.checking.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  private load(caseId: string, page: number): void {
    this.loading.set(true);
    this.cases.movements(caseId, page, PAGE_SIZE).subscribe({
      next: (result) => {
        this.loading.set(false);
        this.page = page;
        this.total.set(result.count);
        this.movements.update((list) =>
          page === 0 ? result.results : [...list, ...result.results],
        );
      },
      error: (err: unknown) => {
        this.loading.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
