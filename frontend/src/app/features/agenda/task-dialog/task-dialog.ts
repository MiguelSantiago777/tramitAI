import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { catchError, of } from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { TenantService } from '../../../core/tenant/tenant.service';
import { ClientPicker, ClientRef } from '../../../shared/client-picker/client-picker';
import {
  TASK_KIND_LABELS,
  TASK_PRIORITY_LABELS,
  Task,
  TaskInput,
  TaskKind,
  TaskPriority,
  todayIso,
} from '../agenda.models';
import { AgendaService } from '../agenda.service';

export interface TaskDialogData {
  task?: Task;
  /** Valores iniciais para tarefa nova (ex.: aberta da ficha do cliente ou do processo). */
  defaults?: {
    client?: ClientRef;
    legal_case_id?: string;
    case_number?: string;
    kind?: TaskKind;
  };
}

@Component({
  selector: 'app-task-dialog',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ClientPicker,
  ],
  template: `
    <h2 mat-dialog-title>{{ editing ? 'Editar tarefa' : 'Nova tarefa' }}</h2>
    <mat-dialog-content>
      <form [formGroup]="form" class="dialog-form" (ngSubmit)="save()" id="task-form">
        <mat-form-field appearance="outline" class="span-2">
          <mat-label>O que precisa ser feito</mat-label>
          <input matInput formControlName="title" cdkFocusInitial />
          @if (form.controls.title.hasError('required')) {
            <mat-error>Descreva a tarefa.</mat-error>
          }
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Tipo</mat-label>
          <mat-select formControlName="kind">
            @for (k of kinds; track k[0]) {
              <mat-option [value]="k[0]">{{ k[1] }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Prioridade</mat-label>
          <mat-select formControlName="priority">
            @for (p of priorities; track p[0]) {
              <mat-option [value]="p[0]">{{ p[1] }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>{{
            form.controls.kind.value === 'DEADLINE' ? 'Data limite' : 'Data'
          }}</mat-label>
          <input matInput type="date" formControlName="due_date" />
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Hora (opcional)</mat-label>
          <input matInput type="time" formControlName="due_time" />
        </mat-form-field>

        <mat-form-field appearance="outline" class="span-2">
          <mat-label>Responsável</mat-label>
          <mat-select formControlName="assignee_id">
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

        <mat-form-field appearance="outline" class="span-2">
          <mat-label>Detalhes (opcional)</mat-label>
          <textarea matInput formControlName="description" rows="3"></textarea>
        </mat-form-field>
      </form>
      @if (error(); as message) {
        <p class="error-text" role="alert">{{ message }}</p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      @if (editing && data.task?.status === 'OPEN') {
        <button
          mat-button
          type="button"
          class="dialog-danger"
          [disabled]="busy()"
          (click)="cancelTask()"
        >
          Cancelar tarefa
        </button>
        <span class="dialog-spacer"></span>
      }
      <button mat-button type="button" mat-dialog-close>Fechar</button>
      <button mat-flat-button type="submit" form="task-form" [disabled]="busy()">Salvar</button>
    </mat-dialog-actions>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskDialog {
  readonly data = inject<TaskDialogData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<TaskDialog, Task>);
  private readonly api = inject(AgendaService);

  readonly kinds = Object.entries(TASK_KIND_LABELS) as [TaskKind, string][];
  readonly priorities = Object.entries(TASK_PRIORITY_LABELS) as [TaskPriority, string][];
  readonly members = toSignal(
    inject(TenantService)
      .members()
      .pipe(catchError(() => of([]))),
    { initialValue: [] },
  );

  readonly editing = !!this.data.task;
  readonly caseNumber = this.data.task?.case_number || this.data.defaults?.case_number || '';
  private readonly caseId =
    this.data.task?.legal_case_id ?? this.data.defaults?.legal_case_id ?? null;

  readonly client = signal<ClientRef | null>(
    this.data.task?.client_id
      ? { id: this.data.task.client_id, name: this.data.task.client_name }
      : (this.data.defaults?.client ?? null),
  );
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  readonly form = inject(NonNullableFormBuilder).group({
    title: [this.data.task?.title ?? '', [Validators.required, Validators.maxLength(200)]],
    kind: [this.data.task?.kind ?? this.data.defaults?.kind ?? ('TASK' as TaskKind)],
    priority: [this.data.task?.priority ?? ('NORMAL' as TaskPriority)],
    due_date: [this.data.task?.due_date ?? (this.editing ? '' : todayIso())],
    due_time: [(this.data.task?.due_time ?? '').slice(0, 5)],
    assignee_id: [this.data.task?.assignee_id ?? (null as string | null)],
    description: [this.data.task?.description ?? ''],
  });

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    const input: TaskInput = {
      title: v.title.trim(),
      description: v.description,
      kind: v.kind,
      priority: v.priority,
      due_date: v.due_date || null,
      due_time: v.due_time || null,
      assignee_id: v.assignee_id,
      client_id: this.client()?.id ?? null,
      legal_case_id: this.caseId,
    };
    const task = this.data.task;
    this.submit(task ? this.api.updateTask(task.id, input) : this.api.createTask(input));
  }

  cancelTask(): void {
    const task = this.data.task;
    if (task) {
      this.submit(this.api.updateTask(task.id, { status: 'CANCELED' }));
    }
  }

  private submit(request: ReturnType<AgendaService['createTask']>): void {
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
