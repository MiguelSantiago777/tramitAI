import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import {
  Subject,
  catchError,
  debounceTime,
  distinctUntilChanged,
  interval,
  merge,
  of,
  startWith,
  switchMap,
} from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { formatPhone } from '../../../shared/br';
import { Conversation } from '../inbox.models';
import { InboxService } from '../inbox.service';
import { Thread } from '../thread/thread';

/** Intervalo de atualização da lista (sem websocket por enquanto). */
export const INBOX_POLL_MS = 10_000;

@Component({
  selector: 'app-inbox',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
    Thread,
  ],
  templateUrl: './inbox.html',
  styleUrl: './inbox.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Inbox {
  private readonly inbox = inject(InboxService);

  /** Parâmetro de rota `:id` (conversa aberta). */
  readonly id = input<string>();

  readonly search = new FormControl('', { nonNullable: true });
  readonly filter = new FormControl<'all' | 'unread' | 'closed'>('all', { nonNullable: true });
  readonly conversations = signal<Conversation[]>([]);
  readonly error = signal<string | null>(null);
  private readonly refresh$ = new Subject<void>();

  constructor() {
    merge(
      interval(INBOX_POLL_MS),
      this.refresh$,
      this.search.valueChanges.pipe(debounceTime(300), distinctUntilChanged()),
      this.filter.valueChanges,
    )
      .pipe(
        startWith(null),
        switchMap(() =>
          this.inbox
            .list({
              q: this.search.value,
              unread: this.filter.value === 'unread',
              status: this.filter.value === 'closed' ? 'CLOSED' : 'OPEN',
            })
            .pipe(
              catchError((err: unknown) => {
                this.error.set(toApiError(err).message);
                return of(null);
              }),
            ),
        ),
        takeUntilDestroyed(),
      )
      .subscribe((page) => {
        if (page) {
          this.error.set(null);
          this.conversations.set(page.results);
        }
      });
  }

  title(c: Conversation): string {
    return c.client_name || c.contact_name || formatPhone(c.phone);
  }

  /** Chamado pela thread quando algo muda (envio, leitura, vínculo). */
  onThreadChanged(): void {
    this.refresh$.next();
  }
}
