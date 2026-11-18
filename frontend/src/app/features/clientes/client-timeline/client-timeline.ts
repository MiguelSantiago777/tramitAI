import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';

import { toApiError } from '../../../core/http/api-error';
import { EventDialog } from '../../agenda/event-dialog/event-dialog';
import { TaskDialog } from '../../agenda/task-dialog/task-dialog';
import { NOTE_KIND_LABELS, NoteKind, TimelineItem, TimelineType } from '../client.models';
import { ClientsService } from '../clients.service';
import { DocumentsService } from '../../../shared/documents/documents.service';

const ICONS: Record<TimelineType, string> = {
  note: 'sticky_note_2',
  task: 'task_alt',
  task_done: 'check_circle',
  event: 'event',
  message: 'chat',
  case: 'gavel',
  movement: 'timeline',
  document: 'attach_file',
  term: 'verified_user',
};

/** Ficha 360°: registrar atendimento, atalhos e linha do tempo do cliente. */
@Component({
  selector: 'app-client-timeline',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
  ],
  templateUrl: './client-timeline.html',
  styleUrl: './client-timeline.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ClientTimeline {
  private readonly api = inject(ClientsService);
  private readonly dialog = inject(MatDialog);
  private readonly documents = inject(DocumentsService);

  readonly clientId = input.required<string>();
  readonly clientName = input('');

  readonly kinds = Object.entries(NOTE_KIND_LABELS) as [NoteKind, string][];
  readonly kind = new FormControl<NoteKind>('CALL', { nonNullable: true });
  readonly body = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, Validators.maxLength(5000)],
  });

  readonly items = signal<TimelineItem[]>([]);
  readonly nextBefore = signal<string | null>(null);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);

  constructor() {
    effect(() => {
      const id = this.clientId();
      untracked(() => this.load(id, null));
    });
  }

  icon(item: TimelineItem): string {
    return ICONS[item.type];
  }

  addNote(): void {
    const text = this.body.value.trim();
    if (!text) {
      this.body.markAsTouched();
      return;
    }
    this.saving.set(true);
    this.error.set(null);
    this.api.addNote(this.clientId(), { kind: this.kind.value, body: text }).subscribe({
      next: () => {
        this.saving.set(false);
        this.body.reset('');
        this.load(this.clientId(), null);
      },
      error: (err: unknown) => {
        this.saving.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  newTask(): void {
    this.dialog
      .open(TaskDialog, {
        data: { defaults: { client: { id: this.clientId(), name: this.clientName() } } },
        width: '640px',
        maxWidth: '95vw',
      })
      .afterClosed()
      .subscribe((saved) => saved && this.load(this.clientId(), null));
  }

  newEvent(): void {
    this.dialog
      .open(EventDialog, {
        data: { defaults: { client: { id: this.clientId(), name: this.clientName() } } },
        width: '640px',
        maxWidth: '95vw',
      })
      .afterClosed()
      .subscribe((saved) => saved && this.load(this.clientId(), null));
  }

  openDocument(item: TimelineItem): void {
    const id = item.meta['document_id'];
    if (id) this.documents.open({ id, name: item.body, can_preview: true });
  }

  more(): void {
    this.load(this.clientId(), this.nextBefore());
  }

  private load(id: string, before: string | null): void {
    this.loading.set(true);
    this.api.timeline(id, before).subscribe({
      next: (page) => {
        this.loading.set(false);
        this.items.update((list) => (before ? [...list, ...page.results] : page.results));
        this.nextBefore.set(page.next_before);
      },
      error: (err: unknown) => {
        this.loading.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
