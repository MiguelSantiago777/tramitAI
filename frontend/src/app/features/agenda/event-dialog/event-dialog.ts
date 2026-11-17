import { ChangeDetectionStrategy, Component, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { catchError, of } from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { TenantService } from '../../../core/tenant/tenant.service';
import { ClientPicker, ClientRef } from '../../../shared/client-picker/client-picker';
import {
  CalendarEvent,
  EVENT_KIND_LABELS,
  EventInput,
  EventKind,
  isoDate,
  todayIso,
} from '../agenda.models';
import { AgendaService } from '../agenda.service';

export interface EventDialogData {
  event?: CalendarEvent;
  defaults?: {
    date?: string;
    client?: ClientRef;
    legal_case_id?: string;
    case_number?: string;
    kind?: EventKind;
  };
}

function timeOf(iso: string | null): string {
  if (!iso) {
    return '';
  }
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** Junta data e hora locais num ISO com o fuso do navegador. */
function combine(date: string, time: string): string {
  return new Date(`${date}T${time || '00:00'}:00`).toISOString();
}

@Component({
  selector: 'app-event-dialog',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    ClientPicker,
  ],
  template: `
    <h2 mat-dialog-title>{{ editing ? 'Editar compromisso' : 'Novo compromisso' }}</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form" (ngSubmit)="save()" id="event-form">
        <mat-form-field appearance="outline">
          <mat-label>Tipo</mat-label>
          <mat-select formControlName="kind">
            @for (k of kinds; track k[0]) {
              <mat-option [value]="k[0]">{{ k[1] }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Título</mat-label>
          <input matInput formControlName="title" placeholder="Ex.: Audiência de conciliação" />
          @if (form.controls.title.hasError('required')) {
            <mat-error>Dê um título.</mat-error>
          }
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Data</mat-label>
          <input matInput type="date" formControlName="date" />
        </mat-form-field>

        <div class="dialog-row">
          <mat-form-field appearance="outline">
            <mat-label>Início</mat-label>
            <input matInput type="time" formControlName="start" />
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Fim</mat-label>
            <input matInput type="time" formControlName="end" />
          </mat-form-field>
        </div>

        <mat-form-field appearance="outline" class="span-2">
          <mat-label>Local ou link</mat-label>
          <input
            matInput
            formControlName="location"
            placeholder="Ex.: Fórum de Nova Iguaçu, sala 3"
          />
        </mat-form-field>

        <mat-form-field appearance="outline" class="span-2">
          <mat-label>Responsável</mat-label>
          <mat-select formControlName="responsible_id">
            <mat-option [value]="null">Sem responsável</mat-option>
            @for (m of members(); track m.user_id) {
              <mat-option [value]="m.user_id">{{ m.full_name || m.email }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <div class="span-2">
          <app-client-picker [(client)]="client" />
        </div>

        @if (caseNumber) {
          <p class="span-2 muted small">Processo {{ caseNumber }}</p>
        }

        <div class="span-2 toggle-field">
          <mat-slide-toggle formControlName="remind_client">
            Lembrar o cliente pelo WhatsApp na véspera
          </mat-slide-toggle>
          <span class="muted small">
            @if (client()) {
              O lembrete vira um rascunho em Aprovações: só sai depois que alguém aprovar.
            } @else {
              Escolha o cliente para ligar o lembrete.
            }
          </span>
        </div>

        <mat-form-field appearance="outline" class="span-2">
          <mat-label>Observações (opcional)</mat-label>
          <textarea matInput formControlName="notes" rows="2"></textarea>
        </mat-form-field>
      </form>
      @if (error(); as message) {
        <p class="error-text" role="alert">{{ message }}</p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      @if (editing && data.event?.status === 'SCHEDULED') {
        <button
          mat-button
          type="button"
          class="dialog-danger"
          [disabled]="busy()"
          (click)="setStatus('CANCELED')"
        >
          Cancelar
        </button>
        <button mat-button type="button" [disabled]="busy()" (click)="setStatus('DONE')">
          Marcar como realizado
        </button>
        <span class="dialog-spacer"></span>
      }
      <button mat-button type="button" mat-dialog-close>Fechar</button>
      <button mat-flat-button type="submit" form="event-form" [disabled]="busy()">Salvar</button>
    </mat-dialog-actions>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EventDialog {
  readonly data = inject<EventDialogData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<EventDialog, CalendarEvent>);
  private readonly api = inject(AgendaService);

  readonly kinds = Object.entries(EVENT_KIND_LABELS) as [EventKind, string][];
  readonly members = toSignal(
    inject(TenantService)
      .members()
      .pipe(catchError(() => of([]))),
    { initialValue: [] },
  );

  readonly editing = !!this.data.event;
  readonly caseNumber = this.data.event?.case_number || this.data.defaults?.case_number || '';
  private readonly caseId =
    this.data.event?.legal_case_id ?? this.data.defaults?.legal_case_id ?? null;

  readonly client = signal<ClientRef | null>(
    this.data.event?.client_id
      ? { id: this.data.event.client_id, name: this.data.event.client_name }
      : (this.data.defaults?.client ?? null),
  );
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  readonly form = inject(NonNullableFormBuilder).group({
    kind: [this.data.event?.kind ?? this.data.defaults?.kind ?? ('MEETING' as EventKind)],
    title: [this.data.event?.title ?? '', [Validators.required, Validators.maxLength(200)]],
    date: [
      this.data.event
        ? isoDate(new Date(this.data.event.starts_at))
        : (this.data.defaults?.date ?? todayIso()),
      Validators.required,
    ],
    start: [this.data.event ? timeOf(this.data.event.starts_at) : '09:00', Validators.required],
    end: [timeOf(this.data.event?.ends_at ?? null)],
    location: [this.data.event?.location ?? ''],
    responsible_id: [this.data.event?.responsible_id ?? (null as string | null)],
    remind_client: [this.data.event?.remind_client ?? false],
    notes: [this.data.event?.notes ?? ''],
  });

  constructor() {
    // Lembrete só faz sentido com cliente escolhido.
    effect(() => {
      const control = this.form.controls.remind_client;
      if (this.client()) {
        control.enable({ emitEvent: false });
      } else {
        control.setValue(false, { emitEvent: false });
        control.disable({ emitEvent: false });
      }
    });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    const input: EventInput = {
      title: v.title.trim(),
      kind: v.kind,
      starts_at: combine(v.date, v.start),
      ends_at: v.end ? combine(v.date, v.end) : null,
      location: v.location.trim(),
      notes: v.notes,
      responsible_id: v.responsible_id,
      client_id: this.client()?.id ?? null,
      legal_case_id: this.caseId,
      remind_client: !!this.client() && v.remind_client,
    };
    const event = this.data.event;
    this.submit(event ? this.api.updateEvent(event.id, input) : this.api.createEvent(input));
  }

  setStatus(status: 'DONE' | 'CANCELED'): void {
    const event = this.data.event;
    if (event) {
      this.submit(this.api.updateEvent(event.id, { status }));
    }
  }

  private submit(request: ReturnType<AgendaService['createEvent']>): void {
    this.busy.set(true);
    this.error.set(null);
    request.subscribe({
      next: (saved) => this.ref.close(saved),
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
