import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { Subscription, filter, switchMap, take, timer } from 'rxjs';

import { toApiError } from '../../core/http/api-error';
import { DocumentsService } from '../../shared/documents/documents.service';
import { FeeAgreement } from '../financeiro/financeiro.models';
import { FinanceiroService } from '../financeiro/financeiro.service';
import { DRAFT_KINDS, DocumentDraft, DraftKind, DraftsService } from './drafts.service';

export interface DraftDialogData {
  clientId?: string | null;
  caseId?: string | null;
  /** Nome para o cabeçalho ("para Maria da Silva"). */
  label?: string;
}

const POLL_MS = 3000;
// A Vera insiste até ~13 min quando o Google está cheio; a tela espera um pouco mais.
const POLL_MAX = 300;

/** Pede uma minuta à Vera e espera ficar pronta (Word + PDF). */
@Component({
  selector: 'app-draft-dialog',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
  ],
  template: `
    <h2 mat-dialog-title>
      Escrever com a Vera
      @if (data.label) {
        <span class="muted small"> · {{ data.label }}</span>
      }
    </h2>

    <mat-dialog-content>
      @if (draft(); as d) {
        @if (d.status === 'PENDING') {
          <p>A Vera está escrevendo a minuta… isso leva de 20 segundos a alguns minutos.</p>
          <mat-progress-bar mode="indeterminate" />
          <p class="muted small">Pode fechar: o Word e o PDF ficam salvos na pasta do cliente.</p>
        } @else if (d.status === 'DONE') {
          <p><strong>Pronto!</strong> Revise antes de usar: é uma minuta.</p>
          @if (d.review_notes) {
            <p class="notes">{{ d.review_notes }}</p>
          }
          @if (d.missing_fields.length > 0) {
            <p class="small">
              Faltou preencher no Word (destacado em amarelo):
              <strong>{{ d.missing_fields.join(', ') }}</strong>
            </p>
          }
          <div class="downloads">
            @if (d.docx_id) {
              <button mat-flat-button type="button" (click)="download(d.docx_id, d.title, 'docx')">
                <span class="icon btn-icon">description</span>Baixar Word
              </button>
            }
            @if (d.pdf_id) {
              <button mat-stroked-button type="button" (click)="download(d.pdf_id, d.title, 'pdf')">
                <span class="icon btn-icon">picture_as_pdf</span>Baixar PDF
              </button>
            }
          </div>
        } @else {
          <p class="error-text" role="alert">{{ failure(d) }}</p>
          <button mat-stroked-button type="button" (click)="draft.set(null)">Tentar de novo</button>
        }
      } @else {
        <form class="form" (submit)="$event.preventDefault(); submit()">
          <mat-form-field appearance="outline" subscriptSizing="dynamic">
            <mat-label>Tipo de documento</mat-label>
            <mat-select [formControl]="kind">
              @for (k of kinds; track k.value) {
                <mat-option [value]="k.value">{{ k.label }}</mat-option>
              }
            </mat-select>
          </mat-form-field>

          @if (kind.value === 'FEE_CONTRACT' && agreements().length > 0) {
            <mat-form-field appearance="outline" subscriptSizing="dynamic">
              <mat-label>Honorários cadastrados (opcional)</mat-label>
              <mat-select [formControl]="agreement">
                <mat-option [value]="null">Nenhum: a Vera deixa os valores em branco</mat-option>
                @for (a of agreements(); track a.id) {
                  <mat-option [value]="a.id">{{ a.title }} · R$ {{ a.total_amount }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
          }

          <mat-form-field appearance="outline" subscriptSizing="dynamic">
            <mat-label>Título</mat-label>
            <input
              matInput
              [formControl]="title"
              maxlength="200"
              placeholder="Ex.: Petição inicial - dano moral"
            />
          </mat-form-field>

          <mat-form-field appearance="outline">
            <mat-label>O que a Vera deve escrever</mat-label>
            <textarea
              matInput
              [formControl]="instructions"
              rows="7"
              maxlength="6000"
              [placeholder]="hint()"
            ></textarea>
            <mat-hint
              >Escreva "o cliente" em vez do nome. Nome, CPF, telefone e valores entram sozinhos
              depois, aqui no TramitAI: não vão para a IA.</mat-hint
            >
          </mat-form-field>

          @if (error(); as message) {
            <p class="error-text" role="alert">{{ message }}</p>
          }
        </form>
      }
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button type="button" mat-dialog-close>Fechar</button>
      @if (!draft()) {
        <button mat-flat-button type="button" [disabled]="busy()" (click)="submit()">
          <span class="icon btn-icon">auto_awesome</span>Escrever
        </button>
      }
    </mat-dialog-actions>
  `,
  styles: `
    .form {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding-top: 4px;
      min-width: min(560px, 80vw);
    }
    .notes {
      padding: 8px 12px;
      border-radius: var(--tm-radius);
      background: var(--mat-sys-secondary-container);
      color: var(--mat-sys-on-secondary-container);
    }
    .downloads {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DraftDialog {
  readonly data = inject<DraftDialogData>(MAT_DIALOG_DATA);
  private readonly api = inject(DraftsService);
  private readonly documents = inject(DocumentsService);
  private readonly finance = inject(FinanceiroService);
  private readonly destroyRef = inject(DestroyRef);

  readonly kinds = DRAFT_KINDS;
  readonly kind = new FormControl<DraftKind>('PETITION', { nonNullable: true });
  readonly title = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, Validators.maxLength(200)],
  });
  readonly instructions = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, Validators.maxLength(6000)],
  });
  readonly agreement = new FormControl<string | null>(null);

  readonly agreements = signal<FeeAgreement[]>([]);
  readonly draft = signal<DocumentDraft | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  private readonly kindValue = toSignal(this.kind.valueChanges, { initialValue: this.kind.value });
  readonly hint = computed(() => DRAFT_KINDS.find((k) => k.value === this.kindValue())?.hint ?? '');
  private poll?: Subscription;

  constructor() {
    if (this.data.clientId) {
      this.finance.agreements(this.data.clientId).subscribe({
        next: (page) => this.agreements.set(page.results),
        error: () => this.agreements.set([]),
      });
    }
  }

  submit(): void {
    if (this.title.invalid || this.instructions.invalid) {
      this.title.markAsTouched();
      this.instructions.markAsTouched();
      this.error.set('Preencha o título e o que a Vera deve escrever.');
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    this.api
      .create({
        kind: this.kind.value,
        title: this.title.value.trim(),
        instructions: this.instructions.value.trim(),
        client_id: this.data.clientId ?? null,
        legal_case_id: this.data.caseId ?? null,
        fee_agreement_id: this.kind.value === 'FEE_CONTRACT' ? this.agreement.value : null,
      })
      .subscribe({
        next: (draft) => {
          this.busy.set(false);
          this.draft.set(draft);
          this.watch(draft.id);
        },
        error: (err: unknown) => {
          this.busy.set(false);
          const apiError = toApiError(err);
          const details = Object.values(apiError.details ?? {})
            .flat()
            .filter((d): d is string => typeof d === 'string');
          this.error.set(details.length > 0 ? details.join(' ') : apiError.message);
        },
      });
  }

  download(id: string, title: string, ext: 'docx' | 'pdf'): void {
    this.documents.download({ id, name: `${title}.${ext}` });
  }

  failure(d: DocumentDraft): string {
    if (d.error_code === 'ai_limit') {
      return 'A Vera já usou todas as mensagens do plano neste mês.';
    }
    if (['rate_limited', 'connection', 'http_503', 'http_500'].includes(d.error_code)) {
      return 'A IA está sobrecarregada agora. Tente de novo em alguns minutos.';
    }
    return 'A Vera não conseguiu escrever esta minuta. Tente reformular o pedido.';
  }

  private watch(id: string): void {
    this.poll?.unsubscribe();
    this.poll = timer(POLL_MS, POLL_MS)
      .pipe(
        take(POLL_MAX),
        switchMap(() => this.api.get(id)),
        filter((d) => {
          this.draft.set(d);
          return d.status !== 'PENDING';
        }),
        take(1),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }
}
