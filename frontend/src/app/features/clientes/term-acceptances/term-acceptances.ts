import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';

import { toApiError } from '../../../core/http/api-error';
import { AcceptanceChannel, CHANNEL_LABELS, TermAcceptance } from '../client.models';
import { ClientsService } from '../clients.service';

/** Aceites do termo de ciência de IA de um cliente + registro de novo aceite. */
@Component({
  selector: 'app-term-acceptances',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
  ],
  template: `
    <section class="form-card">
      <h2>Termo de ciência de IA</h2>
      @if (acceptances().length === 0) {
        <p class="muted">Este cliente ainda não aceitou o termo de uso de IA.</p>
      } @else {
        <ul class="plain-list">
          @for (a of acceptances(); track a.id) {
            <li>
              <strong>Versão {{ a.term_version }}</strong
              >, aceita em {{ a.accepted_at | date: 'dd/MM/yyyy HH:mm' }} ({{
                channelLabels[a.channel]
              }})
              @if (a.evidence) {
                · {{ a.evidence }}
              }
              @if (a.recorded_by_name) {
                <span class="muted"> · registrado por {{ a.recorded_by_name }}</span>
              }
            </li>
          }
        </ul>
      }

      <form [formGroup]="form" (ngSubmit)="register()" class="inline-form">
        <mat-form-field appearance="outline" subscriptSizing="dynamic">
          <mat-label>Canal</mat-label>
          <mat-select formControlName="channel">
            @for (option of channelOptions; track option[0]) {
              <mat-option [value]="option[0]">{{ option[1] }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Evidência (opcional)</mat-label>
          <input
            matInput
            formControlName="evidence"
            placeholder="Ex.: assinado em papel, pasta 12"
          />
        </mat-form-field>
        <button mat-stroked-button type="submit" [disabled]="saving()">Registrar aceite</button>
      </form>
      <p class="muted small">
        Registra o aceite da versão vigente do termo, com data e hora de agora. Pelo WhatsApp, o
        registro será automático (Etapa 3).
      </p>
      @if (error(); as message) {
        <p class="error-text" role="alert">{{ message }}</p>
      }
    </section>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TermAcceptances {
  private readonly clients = inject(ClientsService);
  private readonly snackBar = inject(MatSnackBar);

  readonly clientId = input.required<string>();
  readonly channelLabels = CHANNEL_LABELS;
  readonly channelOptions = Object.entries(CHANNEL_LABELS) as [AcceptanceChannel, string][];

  readonly form = inject(NonNullableFormBuilder).group({
    channel: ['IN_PERSON' as AcceptanceChannel, Validators.required],
    evidence: ['', Validators.maxLength(255)],
  });
  readonly acceptances = signal<TermAcceptance[]>([]);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);

  constructor() {
    effect(() => this.load(this.clientId()));
  }

  register(): void {
    this.saving.set(true);
    this.error.set(null);
    this.clients.registerTermAcceptance(this.clientId(), this.form.getRawValue()).subscribe({
      next: (created) => {
        this.saving.set(false);
        this.acceptances.update((list) => [created, ...list]);
        this.form.controls.evidence.reset('');
        this.snackBar.open('Aceite registrado.', undefined, { duration: 3000 });
      },
      error: (err: unknown) => {
        this.saving.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  private load(clientId: string): void {
    this.clients.termAcceptances(clientId).subscribe({
      next: (list) => this.acceptances.set(list),
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }
}
