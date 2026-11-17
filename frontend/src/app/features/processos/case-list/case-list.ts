import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { Router, RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged, merge } from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { CASE_STATUS_LABELS, CaseStatus, LegalCase } from '../case.models';
import { CasesService } from '../cases.service';

@Component({
  selector: 'app-case-list',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatPaginatorModule,
    MatProgressBarModule,
    MatSelectModule,
    MatTableModule,
  ],
  templateUrl: './case-list.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CaseList {
  private readonly cases = inject(CasesService);
  private readonly router = inject(Router);

  readonly columns = ['cnj', 'tribunal', 'clients', 'classe', 'status'];
  readonly statusLabels = CASE_STATUS_LABELS;
  readonly statusOptions = Object.entries(CASE_STATUS_LABELS) as [CaseStatus, string][];

  readonly search = new FormControl('', { nonNullable: true });
  readonly status = new FormControl<CaseStatus | ''>('ACTIVE', { nonNullable: true });

  readonly rows = signal<LegalCase[]>([]);
  readonly total = signal(0);
  readonly pageIndex = signal(0);
  readonly pageSize = signal(25);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  constructor() {
    merge(
      this.search.valueChanges.pipe(debounceTime(300), distinctUntilChanged()),
      this.status.valueChanges,
    )
      .pipe(takeUntilDestroyed(inject(DestroyRef)))
      .subscribe(() => {
        this.pageIndex.set(0);
        this.load();
      });
    this.load();
  }

  statusLabel(row: LegalCase): string {
    return this.statusLabels[row.status];
  }

  clientNames(row: LegalCase): string {
    return row.clients.map((c) => c.client_name).join(', ');
  }

  onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.pageSize.set(event.pageSize);
    this.load();
  }

  open(row: LegalCase): void {
    void this.router.navigate(['/processos', row.id]);
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.cases
      .list({ q: this.search.value, status: this.status.value }, this.pageIndex(), this.pageSize())
      .subscribe({
        next: (page) => {
          this.rows.set(page.results);
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
