import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import {
  FormControl,
  FormGroup,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import {
  MatAutocompleteModule,
  MatAutocompleteSelectedEvent,
} from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router, RouterLink } from '@angular/router';
import { catchError, debounceTime, distinctUntilChanged, filter, map, of, switchMap } from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { applyServerErrors } from '../../../core/http/form-errors';
import { TenantService } from '../../../core/tenant/tenant.service';
import { cnjValidator, formatCnj, onlyDigits } from '../../../shared/br';
import { Client } from '../../clientes/client.models';
import { ClientsService } from '../../clientes/clients.service';
import {
  CASE_ROLE_LABELS,
  CASE_STATUS_LABELS,
  CaseClientRole,
  CaseStatus,
  LegalCase,
  LegalCaseInput,
} from '../case.models';
import { CaseMovements } from '../case-movements/case-movements';
import { CasesService } from '../cases.service';

type ClientRowGroup = FormGroup<{
  client_id: FormControl<string>;
  client_name: FormControl<string>;
  role: FormControl<CaseClientRole>;
}>;
import { DocumentsPanel } from '../../../shared/documents/documents-panel';

@Component({
  selector: 'app-case-form',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatAutocompleteModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    MatSlideToggleModule,
    CaseMovements,
    DocumentsPanel,
  ],
  templateUrl: './case-form.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CaseForm {
  private readonly cases = inject(CasesService);
  private readonly clientsApi = inject(ClientsService);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly fb = inject(NonNullableFormBuilder);

  /** Parâmetro de rota `:id` (ausente em /processos/novo). */
  readonly id = input<string>();

  readonly statusOptions = Object.entries(CASE_STATUS_LABELS) as [CaseStatus, string][];
  readonly roleOptions = Object.entries(CASE_ROLE_LABELS) as [CaseClientRole, string][];
  readonly members = toSignal(
    inject(TenantService)
      .members()
      .pipe(catchError(() => of([]))),
    { initialValue: [] },
  );

  readonly form = this.fb.group({
    cnj_number: ['', [Validators.required, cnjValidator]],
    classe: [''],
    assunto: [''],
    orgao_julgador: [''],
    responsible_id: this.fb.control<string | null>(null),
    status: ['ACTIVE' as CaseStatus],
    monitoring_enabled: [true],
    notes: [''],
    clients: this.fb.array<ClientRowGroup>([]),
  });

  /** Campo de busca do autocomplete para adicionar cliente. */
  readonly clientSearch = new FormControl<string | Client>('', { nonNullable: true });
  readonly clientOptions = toSignal(
    this.clientSearch.valueChanges.pipe(
      filter((v): v is string => typeof v === 'string'),
      map((v) => v.trim()),
      debounceTime(250),
      distinctUntilChanged(),
      switchMap((q) =>
        q.length < 2
          ? of([])
          : this.clientsApi.list({ q }, 0, 10).pipe(
              map((page) => page.results),
              catchError(() => of([])),
            ),
      ),
      takeUntilDestroyed(),
    ),
    { initialValue: [] as Client[] },
  );

  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly current = signal<LegalCase | null>(null);

  constructor() {
    effect(() => {
      const id = this.id();
      if (id) {
        this.load(id);
      }
    });
  }

  get clientRows() {
    return this.form.controls.clients;
  }

  clientRow(clientId: string, clientName: string, role: CaseClientRole = 'AUTHOR'): ClientRowGroup {
    return this.fb.group({
      client_id: [clientId],
      client_name: [clientName],
      role: [role],
    });
  }

  displayClient = (value: string | Client | null): string =>
    typeof value === 'string' ? value : (value?.name ?? '');

  addClient(event: MatAutocompleteSelectedEvent): void {
    const client = event.option.value as Client;
    const already = this.clientRows.controls.some((row) => row.value.client_id === client.id);
    if (!already) {
      this.clientRows.push(this.clientRow(client.id, client.name));
    }
    this.clientSearch.setValue('');
  }

  removeClient(index: number): void {
    this.clientRows.removeAt(index);
  }

  formatCnjField(): void {
    const control = this.form.controls.cnj_number;
    if (control.valid) {
      control.setValue(formatCnj(control.value));
    }
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    const input: LegalCaseInput = {
      ...raw,
      cnj_number: onlyDigits(raw.cnj_number),
      clients: raw.clients.map(({ client_id, role }) => ({ client_id, role })),
    };
    const id = this.id();
    const request = id ? this.cases.update(id, input) : this.cases.create(input);

    this.saving.set(true);
    this.error.set(null);
    request.subscribe({
      next: (saved) => {
        this.saving.set(false);
        this.snackBar.open('Processo salvo.', undefined, { duration: 3000 });
        if (id) {
          this.patchForm(saved);
        } else {
          void this.router.navigate(['/processos', saved.id]);
        }
      },
      error: (err: unknown) => {
        this.saving.set(false);
        const leftovers = applyServerErrors(this.form, toApiError(err));
        this.error.set(leftovers.length ? leftovers.join(' ') : null);
      },
    });
  }

  /** Depois de uma consulta ao DataJud: atualiza status e, se o form não foi mexido, os dados. */
  refreshCase(): void {
    const id = this.id();
    if (!id) {
      return;
    }
    this.cases.get(id).subscribe({
      next: (found) => (this.form.dirty ? this.current.set(found) : this.patchForm(found)),
      error: () => undefined,
    });
  }

  private load(id: string): void {
    this.loading.set(true);
    this.cases.get(id).subscribe({
      next: (found) => {
        this.patchForm(found);
        this.loading.set(false);
      },
      error: (err: unknown) => {
        this.error.set(toApiError(err).message);
        this.loading.set(false);
      },
    });
  }

  private patchForm(found: LegalCase): void {
    this.current.set(found);
    this.clientRows.clear();
    for (const c of found.clients) {
      this.clientRows.push(this.clientRow(c.client_id, c.client_name, c.role));
    }
    this.form.patchValue({
      cnj_number: found.cnj_formatted,
      classe: found.classe,
      assunto: found.assunto,
      orgao_julgador: found.orgao_julgador,
      responsible_id: found.responsible_id,
      status: found.status,
      monitoring_enabled: found.monitoring_enabled,
      notes: found.notes,
    });
    this.form.markAsPristine();
  }
}
