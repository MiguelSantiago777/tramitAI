import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { RouterLink } from '@angular/router';

import { toApiError } from '../../../core/http/api-error';
import { TASK_KIND_LABELS, Task, isOverdue, isoDate, todayIso } from '../agenda.models';
import { AgendaService } from '../agenda.service';

/** Uma tarefa: marcar como feita, abrir para editar, ver cliente/processo. */
@Component({
  selector: 'app-task-item',
  imports: [DatePipe, RouterLink, MatCheckboxModule],
  template: `
    <div
      class="task"
      [class.task--done]="task().status !== 'OPEN'"
      [class.task--overdue]="overdue()"
    >
      <mat-checkbox
        [checked]="task().status === 'DONE'"
        [disabled]="busy() || task().status === 'CANCELED'"
        (change)="toggle()"
        [attr.aria-label]="'Concluir: ' + task().title"
      />
      <button type="button" class="task__main" (click)="edit.emit(task())">
        <span class="task__title">{{ task().title }}</span>
        <span class="task__meta">
          @if (task().kind !== 'TASK') {
            <span class="badge" [attr.data-status]="task().kind === 'DEADLINE' ? 'URGENT' : 'NEWS'">
              {{ kindLabel() }}
            </span>
          }
          @if (task().priority === 'HIGH' && task().status === 'OPEN') {
            <span class="badge" data-status="DRAFT">Alta</span>
          }
          @if (task().due_date) {
            <span [class.task__late]="overdue()">
              <span class="icon">event</span>
              {{ dueLabel() }}{{ task().due_time ? ' · ' + task().due_time!.slice(0, 5) : '' }}
            </span>
          }
          @if (task().assignee_name && showAssignee()) {
            <span><span class="icon">person</span>{{ task().assignee_name }}</span>
          }
          @if (task().status === 'CANCELED') {
            <span>Cancelada</span>
          } @else if (task().status === 'DONE' && task().completed_at) {
            <span>Concluída em {{ task().completed_at | date: 'dd/MM HH:mm' }}</span>
          }
        </span>
      </button>
      <span class="task__links">
        @if (task().client_id) {
          <a [routerLink]="['/clientes', task().client_id]">{{ task().client_name }}</a>
        }
        @if (task().legal_case_id) {
          <a [routerLink]="['/processos', task().legal_case_id]" class="mono">{{
            task().case_number
          }}</a>
        }
      </span>
    </div>
    @if (error(); as message) {
      <p class="error-text small" role="alert">{{ message }}</p>
    }
  `,
  styleUrl: './task-item.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskItem {
  private readonly api = inject(AgendaService);

  readonly task = input.required<Task>();
  readonly showAssignee = input(true);
  readonly changed = output<Task>();
  readonly edit = output<Task>();

  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly overdue = computed(() => isOverdue(this.task()));
  readonly kindLabel = computed(() => TASK_KIND_LABELS[this.task().kind]);
  readonly dueLabel = computed(() => {
    const due = this.task().due_date;
    if (!due) {
      return '';
    }
    const today = todayIso();
    if (due === today) {
      return 'Hoje';
    }
    const [y, m, d] = due.split('-');
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    if (due === isoDate(tomorrow)) {
      return 'Amanhã';
    }
    return `${d}/${m}${y !== today.slice(0, 4) ? '/' + y : ''}`;
  });

  toggle(): void {
    const t = this.task();
    this.busy.set(true);
    this.error.set(null);
    const request = t.status === 'DONE' ? this.api.reopenTask(t.id) : this.api.completeTask(t.id);
    request.subscribe({
      next: (updated) => {
        this.busy.set(false);
        this.changed.emit(updated);
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
