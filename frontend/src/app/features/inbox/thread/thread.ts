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
import { MatMenuModule } from '@angular/material/menu';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
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
import { TenantService } from '../../../core/tenant/tenant.service';
import { formatPhone } from '../../../shared/br';
import { fileIcon, formatSize } from '../../../shared/documents/documents.models';
import { MessageMedia } from '../../../shared/documents/message-media';
import { Client } from '../../clientes/client.models';
import { ClientsService } from '../../clientes/clients.service';
import { DraftCard } from '../../aprovacoes/draft-card/draft-card';
import { Draft } from '../../aprovacoes/draft.models';
import { DraftsService } from '../../aprovacoes/drafts.service';
import { PendingDraftsCounter } from '../../aprovacoes/pending-counter';
import {
  Conversation,
  MEDIA_LABELS,
  Message,
  OUTBOUND_STATUS_LABELS,
  QuickReply,
  fillQuickReply,
} from '../inbox.models';
import { InboxService } from '../inbox.service';

export const THREAD_POLL_MS = 5_000;

/** Mesmos formatos que o servidor aceita para documentos. */
export const ATTACHMENT_ACCEPT =
  '.pdf,.jpg,.jpeg,.png,.webp,.heic,.gif,.doc,.docx,.xls,.xlsx,.odt,.ods,.rtf,.txt,.csv,' +
  '.mp3,.ogg,.opus,.m4a,.wav,.mp4,.mov,.zip';

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
    MatMenuModule,
    MatSelectModule,
    MatTooltipModule,
    DraftCard,
    MessageMedia,
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
  /** Arquivo escolhido para enviar; o texto do campo vira a legenda. */
  readonly attachment = signal<File | null>(null);
  readonly attachmentAccept = ATTACHMENT_ACCEPT;
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
  readonly members = toSignal(
    inject(TenantService)
      .members()
      .pipe(catchError(() => of([]))),
    { initialValue: [] },
  );
  readonly quickReplies = signal<QuickReply[]>([]);
  readonly retrying = signal(false);
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
        if (drafts.results.length > 0 || conversation.ai_failed_at) {
          this.retrying.set(false);
        }
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

  pickAttachment(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';
    if (file) {
      this.attachment.set(file);
      this.error.set(null);
    }
  }

  clearAttachment(): void {
    this.attachment.set(null);
  }

  attachmentIcon(file: File): string {
    return fileIcon(file.type);
  }

  attachmentSize(file: File): string {
    return formatSize(file.size);
  }

  canSend(): boolean {
    if (this.sending()) return false;
    const text = this.draft.value.trim();
    if (this.attachment()) return text.length <= 1024;
    return this.draft.valid && text.length > 0;
  }

  send(): void {
    const file = this.attachment();
    if (file) {
      this.sendAttachment(file);
      return;
    }
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

  private sendAttachment(file: File): void {
    const conversation = this.conversation();
    if (!conversation || this.sending()) {
      return;
    }
    this.sending.set(true);
    this.error.set(null);
    this.inbox.sendAttachment(conversation.id, file, this.draft.value.trim()).subscribe({
      next: (message) => {
        this.sending.set(false);
        this.attachment.set(null);
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

  assign(userId: string | null): void {
    this.updateConversation({ assignee_id: userId });
  }

  loadQuickReplies(): void {
    this.inbox.quickReplies().subscribe({
      next: (list) => this.quickReplies.set(list),
      error: () => this.quickReplies.set([]),
    });
  }

  useQuickReply(reply: QuickReply): void {
    const c = this.conversation();
    const text = fillQuickReply(reply.body, c?.client_name || c?.contact_name || '');
    const current = this.draft.value.trim();
    this.draft.setValue(current ? `${current}\n\n${text}` : text);
  }

  retryAi(): void {
    const id = this.conversationId();
    this.retrying.set(true);
    this.inbox.retryAi(id).subscribe({
      next: () => {
        // O aviso some na hora; o rascunho aparece pelo polling quando a Vera terminar.
        this.conversation.update((c) => (c ? { ...c, ai_failed_at: null } : c));
        setTimeout(() => this.retrying.set(false), 60_000);
      },
      error: (err: unknown) => {
        this.retrying.set(false);
        this.error.set(toApiError(err).message);
      },
    });
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
    this.attachment.set(null);
  }

  /** Junta a página mais recente com o que já está na tela (mantém as antigas carregadas). */
  private mergeLatest(latestNewestFirst: Message[]): void {
    const latest = [...latestNewestFirst].reverse();
    const ids = new Set(latest.map((m) => m.id));
    this.messages.update((list) => [...list.filter((m) => !ids.has(m.id)), ...latest]);
  }
}
