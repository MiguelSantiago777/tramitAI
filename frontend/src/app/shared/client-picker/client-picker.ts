import { ChangeDetectionStrategy, Component, effect, inject, input, model } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import {
  MatAutocompleteModule,
  MatAutocompleteSelectedEvent,
} from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { catchError, debounceTime, distinctUntilChanged, map, of, switchMap } from 'rxjs';

import { ClientsService } from '../../features/clientes/clients.service';

export interface ClientRef {
  id: string;
  name: string;
}

/** Campo com busca de cliente (nome, CPF ou telefone). Valor: `[(client)]`. */
@Component({
  selector: 'app-client-picker',
  imports: [
    ReactiveFormsModule,
    MatAutocompleteModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  template: `
    <mat-form-field appearance="outline" class="full" subscriptSizing="dynamic">
      <mat-label>{{ label() }}</mat-label>
      <span matPrefix class="icon search-icon">person_search</span>
      <input
        matInput
        [formControl]="search"
        [matAutocomplete]="auto"
        placeholder="Nome, CPF ou telefone"
      />
      @if (client()) {
        <button mat-icon-button matSuffix type="button" aria-label="Limpar" (click)="clear()">
          <span class="icon">close</span>
        </button>
      }
      <mat-autocomplete
        #auto="matAutocomplete"
        [displayWith]="display"
        (optionSelected)="pick($event)"
      >
        @for (option of options(); track option.id) {
          <mat-option [value]="option">{{ option.name }}</mat-option>
        } @empty {
          @if (typed()) {
            <mat-option disabled>Nenhum cliente encontrado</mat-option>
          }
        }
      </mat-autocomplete>
    </mat-form-field>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ClientPicker {
  private readonly clients = inject(ClientsService);

  readonly label = input('Cliente');
  readonly client = model<ClientRef | null>(null);

  readonly search = new FormControl<string | ClientRef>('', { nonNullable: true });
  readonly typed = toSignal(
    this.search.valueChanges.pipe(map((v) => typeof v === 'string' && v.trim().length >= 2)),
    { initialValue: false },
  );
  readonly options = toSignal(
    this.search.valueChanges.pipe(
      map((v) => (typeof v === 'string' ? v.trim() : '')),
      debounceTime(250),
      distinctUntilChanged(),
      switchMap((q) =>
        q.length < 2
          ? of([] as ClientRef[])
          : this.clients.list({ q }, 0, 8).pipe(
              map((page) => page.results.map((c) => ({ id: c.id, name: c.name }))),
              catchError(() => of([] as ClientRef[])),
            ),
      ),
    ),
    { initialValue: [] as ClientRef[] },
  );

  readonly display = (value: ClientRef | string | null): string =>
    typeof value === 'string' ? value : (value?.name ?? '');

  constructor() {
    effect(() => {
      const current = this.client();
      const shown = this.search.value;
      if (current && (typeof shown === 'string' || shown.id !== current.id)) {
        this.search.setValue(current, { emitEvent: false });
      }
    });
  }

  pick(event: MatAutocompleteSelectedEvent): void {
    this.client.set(event.option.value as ClientRef);
  }

  clear(): void {
    this.client.set(null);
    this.search.setValue('');
  }
}
