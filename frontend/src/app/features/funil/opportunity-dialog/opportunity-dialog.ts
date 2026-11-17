import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { TenantService } from '../../../core/tenant/tenant.service';
import { phoneValidator } from '../../../shared/br';
import { ClientPicker, ClientRef } from '../../../shared/client-picker/client-picker';
import {
  AREA_LABELS,
  Area,
  Opportunity,
  OpportunityInput,
  SOURCE_LABELS,
  Source,
} from '../funil.models';
import { FunilService } from '../funil.service';

export interface OpportunityDialogData {
  opportunity?: Opportunity;
}

@Component({
  selector: 'app-opportunity-dialog',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatButtonToggleModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ClientPicker,
  ],
  template: `
    <h2 mat-dialog-title>{{ editing ? 'Oportunidade' : 'Novo contato no funil' }}</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form" (ngSubmit)="save()" id="opp-form">
        @if (editing) {
          <div class="span-2 client-line">
            <span class="muted small">Cliente</span>
            <a [routerLink]="['/clientes', data.opportunity!.client_id]" mat-dialog-close>
              {{ data.opportunity!.client_name }}
            </a>
            @if (data.opportunity!.conversation_id) {
              <a [routerLink]="['/inbox', data.opportunity!.conversation_id]" mat-dialog-close>
                Abrir conversa
              </a>
            }
          </div>
        } @else {
          <mat-button-toggle-group
            class="span-2"
            [value]="mode()"
            (change)="mode.set($event.value)"
            aria-label="Quem é"
          >
            <mat-button-toggle value="new">Pessoa nova</mat-button-toggle>
            <mat-button-toggle value="existing">Cliente já cadastrado</mat-button-toggle>
          </mat-button-toggle-group>
          @if (mode() === 'existing') {
            <div class="span-2">
              <app-client-picker [(client)]="client" />
            </div>
          } @else {
            <mat-form-field appearance="outline">
              <mat-label>Nome</mat-label>
              <input matInput formControlName="new_client_name" />
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Telefone / WhatsApp</mat-label>
              <input matInput formControlName="new_client_phone" placeholder="(21) 99999-9999" />
              @if (form.controls.new_client_phone.hasError('phone')) {
                <mat-error>Telefone inválido.</mat-error>
              }
            </mat-form-field>
          }
        }

        <mat-form-field appearance="outline" class="span-2">
          <mat-label>Assunto</mat-label>
          <input matInput formControlName="title" placeholder="Ex.: Demissão sem justa causa" />
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Área</mat-label>
          <mat-select formControlName="area">
            <mat-option value="">Não definida</mat-option>
            @for (a of areas; track a[0]) {
              <mat-option [value]="a[0]">{{ a[1] }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Como chegou</mat-label>
          <mat-select formControlName="source">
            @for (s of sources; track s[0]) {
              <mat-option [value]="s[0]">{{ s[1] }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Honorários estimados (R$)</mat-label>
          <input matInput type="number" min="0" step="100" formControlName="estimated_value" />
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Responsável</mat-label>
          <mat-select formControlName="owner_id">
            <mat-option [value]="null">Ninguém</mat-option>
            @for (m of members(); track m.user_id) {
              <mat-option [value]="m.user_id">{{ m.full_name || m.email }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline" class="span-2">
          <mat-label>Observações</mat-label>
          <textarea matInput formControlName="notes" rows="3"></textarea>
        </mat-form-field>

        @if (data.opportunity?.lost_reason) {
          <p class="span-2 muted small">
            Motivo de não contratar: {{ data.opportunity!.lost_reason }}
          </p>
        }
      </form>
      @if (error(); as message) {
        <p class="error-text" role="alert">{{ message }}</p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" mat-dialog-close>Fechar</button>
      <button mat-flat-button type="submit" form="opp-form" [disabled]="busy()">Salvar</button>
    </mat-dialog-actions>
  `,
  styles: `
    .client-line {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 12px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OpportunityDialog {
  readonly data = inject<OpportunityDialogData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<OpportunityDialog, Opportunity>);
  private readonly api = inject(FunilService);

  readonly areas = Object.entries(AREA_LABELS) as [Area, string][];
  readonly sources = Object.entries(SOURCE_LABELS) as [Source, string][];
  readonly members = toSignal(
    inject(TenantService)
      .members()
      .pipe(catchError(() => of([]))),
    { initialValue: [] },
  );

  readonly editing = !!this.data.opportunity;
  readonly mode = signal<'new' | 'existing'>('new');
  readonly client = signal<ClientRef | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  private readonly o = this.data.opportunity;
  readonly form = inject(NonNullableFormBuilder).group({
    new_client_name: [''],
    new_client_phone: ['', phoneValidator],
    title: [this.o?.title ?? '', Validators.maxLength(200)],
    area: [(this.o?.area ?? '') as Area | ''],
    source: [(this.o?.source ?? 'WHATSAPP') as Source],
    estimated_value: [
      this.o?.estimated_value ? Number(this.o.estimated_value) : (null as number | null),
    ],
    owner_id: [this.o?.owner_id ?? (null as string | null)],
    notes: [this.o?.notes ?? ''],
  });

  save(): void {
    const v = this.form.getRawValue();
    const input: OpportunityInput = {
      title: v.title.trim(),
      area: v.area,
      source: v.source,
      estimated_value: v.estimated_value === null ? null : String(v.estimated_value),
      owner_id: v.owner_id,
      notes: v.notes,
    };
    const current = this.data.opportunity;
    if (!current) {
      if (this.mode() === 'existing') {
        if (!this.client()) {
          this.error.set('Escolha o cliente.');
          return;
        }
        input.client_id = this.client()!.id;
      } else {
        if (!v.new_client_name.trim()) {
          this.error.set('Informe o nome da pessoa.');
          return;
        }
        if (this.form.controls.new_client_phone.invalid) {
          return;
        }
        input.new_client_name = v.new_client_name.trim();
        input.new_client_phone = v.new_client_phone;
      }
    }
    this.busy.set(true);
    this.error.set(null);
    const request = current ? this.api.update(current.id, input) : this.api.create(input);
    request.subscribe({
      next: (saved) => this.ref.close(saved),
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
