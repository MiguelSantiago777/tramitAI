import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';

import { toApiError } from '../../../core/http/api-error';
import { formatPhone } from '../../../shared/br';
import {
  DRAFT_STATUS_LABELS,
  Draft,
  FLAG_LABELS,
  INTENT_LABELS,
  ORIGIN_LABELS,
  URGENCY_LABELS,
} from '../draft.models';
import { DraftsService } from '../drafts.service';

/** Um rascunho com edição, aprovar e rejeitar. Usado na fila e dentro da conversa. */
@Component({
  selector: 'app-draft-card',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  templateUrl: './draft-card.html',
  styleUrl: './draft-card.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DraftCard {
  private readonly drafts = inject(DraftsService);

  readonly draft = input.required<Draft>();
  readonly canDecide = input(false);
  /** Na fila mostra contato e link para a conversa; dentro da conversa, não. */
  readonly showContact = input(true);
  readonly decided = output<Draft>();

  readonly body = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, Validators.maxLength(4096)],
  });
  readonly reason = new FormControl('', { nonNullable: true });
  readonly rejecting = signal(false);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  readonly pending = computed(() => this.draft().status === 'DRAFT');
  readonly isMovement = computed(() => this.draft().origin === 'MOVEMENT_UPDATE');
  /** Aviso de andamento com a janela fechada sai por modelo da Meta; o texto vai depois. */
  readonly viaTemplate = computed(() => this.isMovement() && !this.draft().window_open);
  readonly canSend = computed(() => this.draft().window_open || this.isMovement());
  /** Mesmo texto de apps/whatsapp/templates.py (MOVEMENT_UPDATE). */
  readonly templatePreview = computed(() => {
    const d = this.draft();
    const firstName = (d.client_name || d.contact_name).split(' ')[0] || 'tudo bem';
    return (
      `Olá, ${firstName}! Há uma atualização no seu processo nº ${d.case_number}. ` +
      'Responda esta mensagem para receber os detalhes.'
    );
  });
  readonly flags = computed(() => this.draft().guardrail_flags.map((f) => FLAG_LABELS[f] ?? f));
  readonly originLabel = computed(() => ORIGIN_LABELS[this.draft().origin]);
  readonly statusLabel = computed(() => DRAFT_STATUS_LABELS[this.draft().status]);
  readonly intentLabel = computed(() => INTENT_LABELS[this.draft().intent] ?? '');
  readonly urgencyLabel = computed(() => URGENCY_LABELS[this.draft().urgency] ?? '');
  readonly contact = computed(() => {
    const d = this.draft();
    return d.client_name || d.contact_name || formatPhone(d.phone);
  });

  constructor() {
    effect(() => {
      const d = this.draft();
      this.body.reset(d.final_body || d.generated_body);
    });
  }

  approve(): void {
    if (this.body.invalid || this.busy()) {
      return;
    }
    const d = this.draft();
    const edited = this.body.value.trim() !== d.generated_body.trim();
    this.run(this.drafts.approve(d.id, edited ? this.body.value : undefined));
  }

  confirmReject(): void {
    this.run(this.drafts.reject(this.draft().id, this.reason.value));
  }

  private run(request: ReturnType<DraftsService['approve']>): void {
    this.busy.set(true);
    this.error.set(null);
    request.subscribe({
      next: (updated) => {
        this.busy.set(false);
        this.rejecting.set(false);
        this.decided.emit(updated);
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
