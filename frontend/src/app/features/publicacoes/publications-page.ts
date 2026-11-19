import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router, RouterLink } from '@angular/router';
import { Observable, debounceTime, distinctUntilChanged, merge, timer } from 'rxjs';

import { toApiError } from '../../core/http/api-error';
import {
  MonitoredOab,
  PUBLICATION_STATUS_LABELS,
  Publication,
  PublicationStatus,
  UFS,
} from './publication.models';
import { PublicationsService } from './publications.service';

const PREVIEW = 420;

/** Intimações e citações do Diário (DJEN) das OABs do escritório. */
@Component({
  selector: 'app-publications-page',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatPaginatorModule,
    MatProgressBarModule,
    MatSelectModule,
  ],
  templateUrl: './publications-page.html',
  styleUrl: './publications-page.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PublicationsPage {
  private readonly api = inject(PublicationsService);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  readonly ufs = UFS;
  readonly statusOptions = Object.entries(PUBLICATION_STATUS_LABELS) as [
    PublicationStatus,
    string,
  ][];

  // OABs
  readonly oabs = signal<MonitoredOab[]>([]);
  readonly number = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, Validators.maxLength(12)],
  });
  readonly uf = new FormControl('', { nonNullable: true, validators: [Validators.required] });
  readonly lawyerName = new FormControl('', { nonNullable: true });
  readonly oabBusy = signal(false);

  // Publicações
  readonly status = new FormControl<PublicationStatus | ''>('NEW', { nonNullable: true });
  readonly search = new FormControl('', { nonNullable: true });
  readonly rows = signal<Publication[]>([]);
  readonly total = signal(0);
  readonly pageIndex = signal(0);
  readonly pageSize = signal(20);
  readonly loading = signal(false);
  readonly busyId = signal<string | null>(null);
  readonly expanded = signal<ReadonlySet<string>>(new Set());
  readonly error = signal<string | null>(null);
  /** Plano sem publicações (402): mostra só o aviso. */
  readonly locked = signal(false);

  constructor() {
    merge(
      this.search.valueChanges.pipe(debounceTime(300), distinctUntilChanged()),
      this.status.valueChanges,
    )
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        this.pageIndex.set(0);
        this.load();
      });
    this.loadOabs();
    this.load();
  }

  // ------------------------------------------------------------------ OABs

  addOab(): void {
    if (this.number.invalid || this.uf.invalid) {
      this.number.markAsTouched();
      this.uf.markAsTouched();
      return;
    }
    this.runOab(
      this.api.createOab({
        number: this.number.value,
        uf: this.uf.value,
        lawyer_name: this.lawyerName.value.trim(),
      }),
      () => {
        this.number.reset('');
        this.lawyerName.reset('');
        this.snackBar.open('OAB cadastrada. Buscando as publicações dos últimos 7 dias…', 'OK', {
          duration: 5000,
        });
        this.refreshSoon();
      },
    );
  }

  toggleOab(oab: MonitoredOab): void {
    this.runOab(this.api.updateOab(oab.id, { is_active: !oab.is_active }));
  }

  removeOab(oab: MonitoredOab): void {
    this.runOab(this.api.deleteOab(oab.id), () =>
      this.snackBar.open('OAB removida. As publicações já recebidas continuam aqui.', 'OK', {
        duration: 4000,
      }),
    );
  }

  checkOab(oab: MonitoredOab): void {
    this.runOab(this.api.checkOab(oab.id), () => {
      this.snackBar.open('Buscando no Diário… a lista atualiza em alguns segundos.', 'OK', {
        duration: 4000,
      });
      this.refreshSoon();
    });
  }

  oabError(oab: MonitoredOab): string {
    if (!oab.last_error) {
      return '';
    }
    return oab.last_error === 'http_429'
      ? 'O Diário pediu para esperar; tentamos de novo sozinhos.'
      : 'A última busca falhou; tentamos de novo no próximo ciclo.';
  }

  // ------------------------------------------------------------------ publicações

  isExpanded(p: Publication): boolean {
    return this.expanded().has(p.id);
  }

  isLong(p: Publication): boolean {
    return p.text.length > PREVIEW;
  }

  preview(p: Publication): string {
    if (this.isExpanded(p) || !this.isLong(p)) {
      return p.text;
    }
    return p.text.slice(0, PREVIEW).trimEnd() + '…';
  }

  toggleText(p: Publication): void {
    const next = new Set(this.expanded());
    if (next.has(p.id)) {
      next.delete(p.id);
    } else {
      next.add(p.id);
    }
    this.expanded.set(next);
  }

  mark(p: Publication, status: PublicationStatus): void {
    this.busyId.set(p.id);
    this.api.mark(p.id, status).subscribe({
      next: () => {
        this.busyId.set(null);
        this.load();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  createCase(p: Publication): void {
    this.busyId.set(p.id);
    this.api.createCase(p.id).subscribe({
      next: ({ case_id }) => {
        this.busyId.set(null);
        void this.router.navigate(['/processos', case_id]);
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.pageSize.set(event.pageSize);
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .list({ status: this.status.value, q: this.search.value }, this.pageIndex(), this.pageSize())
      .subscribe({
        next: (page) => {
          this.rows.set(page.results);
          this.total.set(page.count);
          this.loading.set(false);
        },
        error: (err: unknown) => {
          this.loading.set(false);
          this.handleError(err);
        },
      });
  }

  private loadOabs(): void {
    this.api.listOabs().subscribe({
      next: (page) => this.oabs.set(page.results),
      error: (err: unknown) => this.handleError(err),
    });
  }

  /** A busca roda na fila: recarrega depois de alguns segundos. */
  private refreshSoon(): void {
    timer(6000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.loadOabs();
        this.load();
      });
  }

  private runOab(request: Observable<unknown>, done?: () => void): void {
    this.oabBusy.set(true);
    this.error.set(null);
    request.subscribe({
      next: () => {
        this.oabBusy.set(false);
        done?.();
        this.loadOabs();
      },
      error: (err: unknown) => {
        this.oabBusy.set(false);
        this.handleError(err);
      },
    });
  }

  private fail(err: unknown): void {
    this.busyId.set(null);
    this.handleError(err);
  }

  private handleError(err: unknown): void {
    const apiError = toApiError(err);
    if (apiError.code === 'plan_feature') {
      this.locked.set(true);
    }
    const details = Object.values(apiError.details ?? {})
      .flat()
      .filter((d): d is string => typeof d === 'string');
    this.error.set(details.length > 0 ? details.join(' ') : apiError.message);
  }
}
