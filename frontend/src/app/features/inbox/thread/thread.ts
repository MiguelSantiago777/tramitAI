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
import { takeUntilDestroyed, toObservable, toSignal } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import {
  MatAutocompleteModule,
  MatAutocompleteSelectedEvent,
} from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import {
  catchError,
  debounceTime,
  distinctUntilChanged,
  filter,
  forkJoin,
  interval,
  map,
  of,
  startWith,
  switchMap,
} from 'rxjs';

import { AuthService } from '../../../core/auth/auth.service';
import { toApiError } from '../../../core/http/api-error';
import { formatPhone } from '../../../shared/br';
import { Client } from '../../clientes/client.models';
import { ClientsService } from '../../clientes/clients.service';
import { DraftCard } from '../../aprovacoes/draft-card/draft-card';
import { Draft } from '../../aprovacoes/draft.models';
import { DraftsService } from '../../aprovacoes/drafts.service';
import { PendingDraftsCounter } from '../../aprovacoes/pending-counter';
import { Conversation, MEDIA_LABELS, Message, OUTBOUND_STATUS_LABELS } from '../inbox.models';
import { InboxService } from '../inbox.service';

export const THREAD_POLL_MS = 5_000;

@Component({
  selector: 'app-thread',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatAutocompleteModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    DraftCard,
  ],
  templateUrl: './thread.html',
  styleUrl: './thread.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Thread {
  private readonly inbox = inject(InboxService);
  private readonly clientsApi = inject(ClientsService);
  private readonly draftsApi = inject(DraftsService);
  private readonly counter = inject(PendingDraftsCounter);
  private readonly auth = inject(AuthService);

  readonly conversationId = input.required<string>();
  /** Avisa o inbox para atualizar a lista. */
  readonly changed = output<void>();

  readonly conversation = signal<Conversation | null>(null);
  /** Ordem cronológica (a API devolve da mais recente para a mais antiga). */
  readonly messages = signal<Message[]>([]);
  readonly hasOlder = signal(false);
  readonly error = signal<string | null>(null);
  readonly sending = signal(false);
  /** Rascunhos aguardando aprovação nesta conversa. */
  readonly pendingDrafts = signal<Draft[]>([]);
  readonly canDecide = computed(() => this.auth.session()?.can_approve ?? false);
  private olderPage = 1;

  readonly draft = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, Validators.maxLength(4096)],
  });
  readonly clientSearch = new FormControl<string | Client>('', { nonNullable: true });
  readonly clientOptions = toSignal(
    this.clientSearch.valueChanges.pipe(
      filter((v): v is string => typeof v === 'string'),
      map((v) => v.trim()),
      debounceTime(250),
      distinctUntilChanged(),
      switchMap((q) =>
        q.length < 2
          ? of([])
          : this.clientsApi.list({ q }, 0, 10).pipe(
              map((page) => page.results),
              catchError(() => of([])),
            ),
      ),
    ),
    { initialValue: [] as Client[] },
  );

  readonly title = computed(() => {
    const c = this.conversation();
    return c ? c.client_name || c.contact_name || formatPhone(c.phone) : '';
  });
  readonly canReply = computed(() => this.conversation()?.window_open ?? false);
  readonly outboundLabels = OUTBOUND_STATUS_LABELS;
  readonly formatPhone = formatPhone;

  constructor() {
    toObservable(this.conversationId)
      .pipe(
        switchMap((id) => {
          this.reset();
          this.inbox.markRead(id).subscribe({ next: () => this.changed.emit(), error: () => null });
          return interval(THREAD_POLL_MS).pipe(
            startWith(0),
            switchMap(() =>
              forkJoin([
                this.inbox.get(id),
                this.inbox.messages(id),
                this.draftsApi.list({ status: 'DRAFT', conversation_id: id }, 0, 10),
              ]).pipe(
                catchError((err: unknown) => {
                  this.error.set(toApiError(err).message);
                  return of(null);
                }),
              ),
            ),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((result) => {
        if (!result) {
          return;
        }
        const [conversation, page, drafts] = result;
        this.conversation.set(conversation);
        this.pendingDrafts.set(drafts.results);
        this.mergeLatest(page.results);
        if (this.olderPage === 1) {
          this.hasOlder.set(page.next !== null);
        }
        if (conversation.unread_count > 0) {
          this.inbox.markRead(conversation.id).subscribe({ error: () => null });
        }
      });
  }

  mediaLabel(m: Message): string {
    return MEDIA_LABELS[m.type] ?? MEDIA_LABELS['other'];
  }

  send(): void {
    const body = this.draft.value.trim();
    const conversation = this.conversation();
    if (!body || !conversation || this.sending()) {
      return;
    }
    this.sending.set(true);
    this.error.set(null);
    this.inbox.send(conversation.id, body).subscribe({
      next: (message) => {
        this.sending.set(false);
        this.draft.reset('');
        this.messages.update((list) => [...list, message]);
        this.changed.emit();
      },
      error: (err: unknown) => {
        this.sending.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  onComposerKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      this.send();
    }
  }

  loadOlder(): void {
    this.olderPage += 1;
    this.inbox.messages(this.conversationId(), this.olderPage).subscribe({
      next: (page) => {
        this.messages.update((list) => [...[...page.results].reverse(), ...list]);
        this.hasOlder.set(page.next !== null);
      },
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }

  displayClient = (value: string | Client | null): string =>
    typeof value === 'string' ? value : (value?.name ?? '');

  linkClient(event: MatAutocompleteSelectedEvent): void {
    const client = event.option.value as Client;
    this.updateConversation({ client_id: client.id });
    this.clientSearch.setValue('');
  }

  linkSuggested(): void {
    const suggested = this.conversation()?.suggested_client_id;
    if (suggested) {
      this.updateConversation({ client_id: suggested });
    }
  }

  onDraftDecided(updated: Draft): void {
    this.pendingDrafts.update((list) => list.filter((d) => d.id !== updated.id));
    this.counter.refresh();
    this.changed.emit();
    if (updated.status === 'APPROVED' || updated.status === 'SENT') {
      this.inbox.messages(this.conversationId()).subscribe({
        next: (page) => this.mergeLatest(page.results),
        error: () => undefined,
      });
    }
  }

  unlinkClient(): void {
    this.updateConversation({ client_id: null });
  }

  toggleStatus(): void {
    const current = this.conversation();
    if (current) {
      this.updateConversation({ status: current.status === 'OPEN' ? 'CLOSED' : 'OPEN' });
    }
  }

  private updateConversation(changes: Parameters<InboxService['update']>[1]): void {
    this.inbox.update(this.conversationId(), changes).subscribe({
      next: (updated) => {
        this.conversation.set(updated);
        this.changed.emit();
      },
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }

  private reset(): void {
    this.conversation.set(null);
    this.messages.set([]);
    this.pendingDrafts.set([]);
    this.hasOlder.set(false);
    this.error.set(null);
    this.olderPage = 1;
    this.draft.reset('');
  }

  /** Junta a página mais recente com o que já está na tela (mantém as antigas carregadas). */
  private mergeLatest(latestNewestFirst: Message[]): void {
    const latest = [...latestNewestFirst].reverse();
    const ids = new Set(latest.map((m) => m.id));
    this.messages.update((list) => [...list.filter((m) => !ids.has(m.id)), ...latest]);
  }
}
