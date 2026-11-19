import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import {
  FormControl,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router, RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { applyServerErrors } from '../../../core/http/form-errors';
import { documentValidator, formatDocument, formatPhone, phoneValidator } from '../../../shared/br';
import {
  CLIENT_KIND_LABELS,
  CLIENT_STATUS_LABELS,
  Client,
  ClientInput,
  ClientKind,
  ClientStatus,
  Tag,
} from '../client.models';
import { ClientsService } from '../clients.service';
import { ClientTimeline } from '../client-timeline/client-timeline';
import { TermAcceptances } from '../term-acceptances/term-acceptances';
import { DocumentsPanel } from '../../../shared/documents/documents-panel';
import { ClientFeesPanel } from '../../financeiro/client-fees-panel';

import { RemoveButton } from '../../lixeira/remove-button';
import { DraftButton } from '../../minutas/draft-button';
@Component({
  selector: 'app-client-form',
  imports: [
    DraftButton,
    RemoveButton,
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    TermAcceptances,
    ClientTimeline,
    DocumentsPanel,
    ClientFeesPanel,
  ],
  templateUrl: './client-form.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ClientForm {
  private readonly clients = inject(ClientsService);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);

  /** Parâmetro de rota `:id` (ausente em /clientes/novo). */
  readonly id = input<string>();

  readonly kindOptions = Object.entries(CLIENT_KIND_LABELS) as [ClientKind, string][];
  readonly statusOptions = Object.entries(CLIENT_STATUS_LABELS) as [ClientStatus, string][];

  private readonly kind = new FormControl<ClientKind>('PF', { nonNullable: true });
  readonly form = inject(NonNullableFormBuilder).group({
    kind: this.kind,
    name: ['', [Validators.required, Validators.maxLength(200)]],
    cpf_cnpj: ['', documentValidator(() => this.kind.value)],
    phone: ['', phoneValidator],
    email: ['', Validators.email],
    status: ['ACTIVE' as ClientStatus],
    notes: [''],
    tag_ids: [[] as string[]],
  });
  readonly tags = toSignal(this.clients.tags().pipe(catchError(() => of([] as Tag[]))), {
    initialValue: [] as Tag[],
  });

  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly client = signal<Client | null>(null);

  constructor() {
    this.form.controls.kind.valueChanges.subscribe(() =>
      this.form.controls.cpf_cnpj.updateValueAndValidity(),
    );
    effect(() => {
      const id = this.id();
      if (id) {
        this.load(id);
      }
    });
  }

  formatDocumentField(): void {
    const control = this.form.controls.cpf_cnpj;
    if (control.valid && control.value) {
      control.setValue(formatDocument(control.value));
    }
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const input: ClientInput = this.form.getRawValue();
    const id = this.id();
    const request = id ? this.clients.update(id, input) : this.clients.create(input);

    this.saving.set(true);
    this.error.set(null);
    request.subscribe({
      next: (saved) => {
        this.saving.set(false);
        this.snackBar.open('Cliente salvo.', undefined, { duration: 3000 });
        if (id) {
          this.patchForm(saved);
        } else {
          void this.router.navigate(['/clientes', saved.id]);
        }
      },
      error: (err: unknown) => {
        this.saving.set(false);
        const leftovers = applyServerErrors(this.form, toApiError(err));
        this.error.set(leftovers.length ? leftovers.join(' ') : null);
      },
    });
  }

  private load(id: string): void {
    this.loading.set(true);
    this.clients.get(id).subscribe({
      next: (client) => {
        this.patchForm(client);
        this.loading.set(false);
      },
      error: (err: unknown) => {
        this.error.set(toApiError(err).message);
        this.loading.set(false);
      },
    });
  }

  private patchForm(client: Client): void {
    this.client.set(client);
    this.form.reset({
      kind: client.kind,
      name: client.name,
      cpf_cnpj: client.cpf_cnpj ? formatDocument(client.cpf_cnpj) : '',
      phone: client.phone ? formatPhone(client.phone) : '',
      email: client.email,
      status: client.status,
      notes: client.notes,
      tag_ids: client.tags.map((t) => t.id),
    });
  }
}
