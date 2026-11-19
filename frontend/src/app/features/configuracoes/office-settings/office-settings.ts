import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import {
  FormArray,
  FormGroup,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';
import { catchError, of } from 'rxjs';

import { AuthService } from '../../../core/auth/auth.service';
import { toApiError } from '../../../core/http/api-error';
import { OfficeSettings, TenantService } from '../../../core/tenant/tenant.service';
import { DAY_NAMES, DayHours, hoursFromDays, daysFromHours } from './business-hours';

/** Configurações do escritório. Alterar: só o titular. */
@Component({
  selector: 'app-office-settings',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
  ],
  template: `
    <header class="page-header">
      <div>
        <h1>Configurações do escritório</h1>
        <p>Como o TramitAI trabalha para o seu escritório.</p>
      </div>
    </header>

    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    <form class="form-card settings" [formGroup]="form" (ngSubmit)="save()">
      <h2>Escritório</h2>
      <mat-form-field appearance="outline" class="full">
        <mat-label>Nome do escritório</mat-label>
        <input matInput formControlName="tenant_name" />
        <mat-hint>Aparece para os clientes no termo de ciência e nas mensagens.</mat-hint>
      </mat-form-field>

      <h2>Vera (inteligência artificial)</h2>
      <div class="setting">
        <mat-slide-toggle formControlName="ai_triage_enabled">
          Vera escreve rascunhos de resposta e de aviso de andamento
        </mat-slide-toggle>
        <span class="muted small">
          Desligado: as mensagens continuam chegando em Conversas e os avisos de andamento usam um
          texto fixo, sem IA.
        </span>
      </div>

      <h2>Triagem automática</h2>
      <div class="setting">
        <mat-slide-toggle formControlName="auto_send_simple_replies">
          Vera conversa sozinha com contatos novos até entender o caso
        </mat-slide-toggle>
        <span class="muted small">
          Só com quem ainda não é cliente e já aceitou o termo de IA. A Vera pergunta nome e o que
          aconteceu, sem dar orientação jurídica. Quando tiver o resumo (ou se for urgente), avisa o
          contato que passou para o advogado e a resposta seguinte espera a sua aprovação. Clientes
          com processo continuam sempre com aprovação.
        </span>
      </div>

      <h2>Horário de atendimento</h2>
      <p class="muted small">
        Fora desse horário, a Vera avisa o contato quando o escritório atende e segue a triagem.
      </p>
      <div class="hours" formArrayName="days">
        @for (day of days.controls; track $index) {
          <div class="hours__row" [formGroupName]="$index">
            <mat-checkbox formControlName="open" class="hours__day">{{
              dayNames[$index]
            }}</mat-checkbox>
            @if (day.controls.open.value) {
              <mat-form-field appearance="outline" subscriptSizing="dynamic">
                <mat-label>Abre</mat-label>
                <input matInput type="time" formControlName="start" />
              </mat-form-field>
              <mat-form-field appearance="outline" subscriptSizing="dynamic">
                <mat-label>Fecha</mat-label>
                <input matInput type="time" formControlName="end" />
              </mat-form-field>
              <mat-checkbox formControlName="hasBreak">Intervalo</mat-checkbox>
              @if (day.controls.hasBreak.value) {
                <mat-form-field appearance="outline" subscriptSizing="dynamic">
                  <mat-label>De</mat-label>
                  <input matInput type="time" formControlName="breakStart" />
                </mat-form-field>
                <mat-form-field appearance="outline" subscriptSizing="dynamic">
                  <mat-label>Até</mat-label>
                  <input matInput type="time" formControlName="breakEnd" />
                </mat-form-field>
              }
            } @else {
              <span class="muted small">Fechado</span>
            }
          </div>
        }
      </div>

      <h2>Agenda da Vera</h2>
      <div class="setting">
        <mat-slide-toggle formControlName="scheduling_enabled">
          Vera oferece horários livres para a consulta inicial
        </mat-slide-toggle>
        <span class="muted small">
          A Vera oferece 3 horários livres dentro do horário de atendimento (sem bater com a agenda),
          pergunta se a pessoa prefere presencial ou online e deixa o horário escolhido como "a
          confirmar" na Agenda. O contato só recebe a confirmação quando você confirmar.
        </span>
      </div>
      @if (form.controls.scheduling_enabled.value) {
        <div class="form-grid">
          <mat-form-field appearance="outline">
            <mat-label>Duração da consulta</mat-label>
            <mat-select formControlName="consult_minutes">
              @for (m of durations; track m) {
                <mat-option [value]="m">{{ m }} minutos</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline">
            <mat-label>Agenda de quem</mat-label>
            <mat-select formControlName="scheduling_user_id">
              <mat-option [value]="null">Titular do escritório</mat-option>
              @for (m of members(); track m.user_id) {
                <mat-option [value]="m.user_id">{{ m.full_name || m.email }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
        </div>
      }

      <h2>Aprovação de mensagens</h2>
      <div class="setting">
        <mat-slide-toggle formControlName="staff_can_approve">
          Pessoas com papel "Equipe" também podem aprovar mensagens
        </mat-slide-toggle>
        <span class="muted small">
          Titular e advogados sempre podem aprovar. Ligue se a sua secretária deve poder enviar.
        </span>
      </div>

      @if (canEdit()) {
        <div class="form-actions">
          <button mat-flat-button type="submit" [disabled]="busy() || form.pristine">Salvar</button>
        </div>
      } @else {
        <p class="muted small">Só o titular pode alterar estas configurações.</p>
      }
    </form>
  `,
  styles: `
    .settings h2 {
      margin-top: 20px;
    }
    .settings h2:first-of-type {
      margin-top: 4px;
    }
    .setting {
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-width: 640px;
    }
    .hours {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .hours__row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px 12px;
      min-height: 48px;
    }
    .hours__row mat-form-field {
      width: 120px;
    }
    .hours__day {
      width: 110px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OfficeSettingsPage {
  private readonly api = inject(TenantService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly session = inject(AuthService).session;
  readonly canEdit = computed(() => this.session()?.role === 'OWNER');

  readonly dayNames = DAY_NAMES;
  readonly durations = [30, 45, 60, 90, 120];
  readonly members = toSignal(this.api.members().pipe(catchError(() => of([]))), {
    initialValue: [],
  });
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  readonly form = this.fb.group({
    tenant_name: ['', [Validators.required, Validators.maxLength(200)]],
    ai_triage_enabled: [true],
    auto_send_simple_replies: [false],
    scheduling_enabled: [false],
    consult_minutes: [60],
    scheduling_user_id: [null as string | null],
    staff_can_approve: [false],
    days: this.fb.array(DAY_NAMES.map(() => this.dayGroup())),
  });

  get days(): FormArray<FormGroup<ReturnType<OfficeSettingsPage['dayGroup']>['controls']>> {
    return this.form.controls.days;
  }

  constructor() {
    this.api.settings().subscribe({
      next: (s) => {
        this.fill(s);
        if (!this.canEdit()) {
          this.form.disable();
        }
      },
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const { days, ...rest } = this.form.getRawValue();
    this.busy.set(true);
    this.error.set(null);
    this.api.updateSettings({ ...rest, business_hours: hoursFromDays(days) }).subscribe({
      next: (s) => {
        this.busy.set(false);
        this.fill(s);
        this.snackBar.open('Configurações salvas.', undefined, { duration: 3000 });
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  private dayGroup(value?: DayHours) {
    return this.fb.group({
      open: [value?.open ?? false],
      start: [value?.start ?? '09:00'],
      end: [value?.end ?? '18:00'],
      hasBreak: [value?.hasBreak ?? true],
      breakStart: [value?.breakStart ?? '12:00'],
      breakEnd: [value?.breakEnd ?? '13:00'],
    });
  }

  private fill(s: OfficeSettings): void {
    this.form.reset({
      tenant_name: s.tenant_name,
      ai_triage_enabled: s.ai_triage_enabled,
      auto_send_simple_replies: s.auto_send_simple_replies,
      scheduling_enabled: s.scheduling_enabled,
      consult_minutes: s.consult_minutes,
      scheduling_user_id: s.scheduling_user_id,
      staff_can_approve: s.staff_can_approve,
      days: daysFromHours(s.business_hours),
    });
  }
}
