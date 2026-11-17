import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { debounceTime, merge } from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { Task, TaskStatus } from '../agenda.models';
import { AgendaService, TaskFilters } from '../agenda.service';
import { TaskDialog, TaskDialogData } from '../task-dialog/task-dialog';
import { TaskItem } from '../task-item/task-item';

type Due = NonNullable<TaskFilters['due']>;

@Component({
  selector: 'app-tasks-page',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    TaskItem,
  ],
  template: `
    <header class="page-header">
      <div>
        <h1>Tarefas e prazos</h1>
        <p>Tudo o que o escritório precisa fazer, com responsável e data.</p>
      </div>
      <button mat-flat-button type="button" (click)="create()">
        <span class="icon btn-icon">add</span>Nova tarefa
      </button>
    </header>

    <div class="filters">
      <mat-button-toggle-group [formControl]="who" aria-label="De quem">
        <mat-button-toggle value="me">Minhas</mat-button-toggle>
        <mat-button-toggle value="">Todas</mat-button-toggle>
        <mat-button-toggle value="none">Sem responsável</mat-button-toggle>
      </mat-button-toggle-group>
      <mat-form-field appearance="outline" subscriptSizing="dynamic">
        <mat-label>Quando</mat-label>
        <mat-select [formControl]="due">
          <mat-option value="">Qualquer data</mat-option>
          <mat-option value="overdue">Atrasadas</mat-option>
          <mat-option value="today">Hoje</mat-option>
          <mat-option value="week">Próximos 7 dias</mat-option>
          <mat-option value="none">Sem data</mat-option>
        </mat-select>
      </mat-form-field>
      <mat-form-field appearance="outline" subscriptSizing="dynamic">
        <mat-label>Situação</mat-label>
        <mat-select [formControl]="status">
          <mat-option value="OPEN">Abertas</mat-option>
          <mat-option value="DONE">Concluídas</mat-option>
          <mat-option value="CANCELED">Canceladas</mat-option>
          <mat-option value="">Todas</mat-option>
        </mat-select>
      </mat-form-field>
      <mat-form-field appearance="outline" class="filters__search" subscriptSizing="dynamic">
        <span matPrefix class="icon search-icon">search</span>
        <mat-label>Buscar</mat-label>
        <input matInput [formControl]="search" placeholder="Título, detalhe ou cliente" />
      </mat-form-field>
    </div>

    @if (loading()) {
      <mat-progress-bar mode="indeterminate" />
    }
    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    <section class="card task-list">
      @for (t of tasks(); track t.id) {
        <app-task-item [task]="t" (changed)="replace($event)" (edit)="open($event)" />
      } @empty {
        @if (!loading()) {
          <div class="empty-state">
            <span class="icon">task_alt</span>
            Nenhuma tarefa por aqui.
          </div>
        }
      }
    </section>
    @if (total() > tasks().length) {
      <p class="muted small">
        Mostrando {{ tasks().length }} de {{ total() }}. Use os filtros para achar o resto.
      </p>
    }
  `,
  styles: `
    .task-list {
      padding: 6px 12px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TasksPage {
  private readonly api = inject(AgendaService);
  private readonly dialog = inject(MatDialog);

  readonly who = new FormControl('me', { nonNullable: true });
  readonly due = new FormControl<Due>('', { nonNullable: true });
  readonly status = new FormControl<TaskStatus | ''>('OPEN', { nonNullable: true });
  readonly search = new FormControl('', { nonNullable: true });

  readonly tasks = signal<Task[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  constructor() {
    merge(
      this.who.valueChanges,
      this.due.valueChanges,
      this.status.valueChanges,
      this.search.valueChanges.pipe(debounceTime(300)),
    )
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.load());
    this.load();
  }

  create(): void {
    this.openDialog({});
  }

  open(task: Task): void {
    this.openDialog({ task });
  }

  replace(updated: Task): void {
    this.tasks.update((list) => list.map((t) => (t.id === updated.id ? updated : t)));
  }

  private openDialog(data: TaskDialogData): void {
    this.dialog
      .open(TaskDialog, { data, width: '640px', maxWidth: '95vw', autoFocus: 'first-tabbable' })
      .afterClosed()
      .subscribe((saved?: Task) => {
        if (saved) {
          this.load();
        }
      });
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .tasks({
        assignee: this.who.value,
        due: this.due.value,
        status: this.status.value,
        q: this.search.value.trim(),
      })
      .subscribe({
        next: (page) => {
          this.loading.set(false);
          this.tasks.set(page.results);
          this.total.set(page.count);
        },
        error: (err: unknown) => {
          this.loading.set(false);
          this.error.set(toApiError(err).message);
        },
      });
  }
}
