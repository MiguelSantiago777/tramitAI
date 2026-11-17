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
import { formatDocument, formatPhone } from '../../../shared/br';
import { CLIENT_STATUS_LABELS, Client, ClientStatus } from '../client.models';
import { ClientsService } from '../clients.service';

@Component({
  selector: 'app-client-list',
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
  templateUrl: './client-list.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ClientList {
  private readonly clients = inject(ClientsService);
  private readonly router = inject(Router);

  readonly columns = ['name', 'cpf_cnpj', 'phone', 'status'];
  readonly statusLabels = CLIENT_STATUS_LABELS;
  readonly statusOptions = Object.entries(CLIENT_STATUS_LABELS) as [ClientStatus, string][];
  readonly formatDocument = formatDocument;
  readonly formatPhone = formatPhone;

  readonly search = new FormControl('', { nonNullable: true });
  readonly status = new FormControl<ClientStatus | ''>('', { nonNullable: true });

  readonly rows = signal<Client[]>([]);
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

  onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.pageSize.set(event.pageSize);
    this.load();
  }

  statusLabel(client: Client): string {
    return this.statusLabels[client.status];
  }

  open(client: Client): void {
    void this.router.navigate(['/clientes', client.id]);
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.clients
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
