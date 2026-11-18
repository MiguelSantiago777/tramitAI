import { DatePipe } from '@angular/common';
import { HttpEventType } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { toApiError } from '../../core/http/api-error';
import {
  ACCEPTED_FILES,
  CATEGORY_LABELS,
  DocumentCategory,
  DocumentItem,
  MAX_FILE_MB,
  fileIcon,
  formatSize,
} from './documents.models';
import { DocumentsService } from './documents.service';

/** Pasta de documentos do cliente ou do processo: enviar, abrir, baixar e apagar. */
@Component({
  selector: 'app-documents-panel',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatMenuModule,
    MatProgressBarModule,
    MatSelectModule,
  ],
  template: `
    <section class="card panel-card">
      <header class="panel-card__header">
        <h2 class="section-title">
          <span class="icon">folder_open</span> Documentos
          @if (docs().length) {
            <span class="muted small">({{ docs().length }})</span>
          }
        </h2>
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="docs__category">
          <mat-label>Tipo do arquivo</mat-label>
          <mat-select [formControl]="category">
            @for (c of categories; track c[0]) {
              <mat-option [value]="c[0]">{{ c[1] }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <button mat-flat-button type="button" [disabled]="uploading()" (click)="picker.click()">
          <span class="icon btn-icon">upload_file</span>Enviar arquivo
        </button>
        <input #picker type="file" hidden multiple [accept]="accepted" (change)="onFiles(picker)" />
      </header>

      <div
        class="docs__drop"
        [class.docs__drop--over]="dragOver()"
        (dragover)="onDragOver($event)"
        (dragleave)="dragOver.set(false)"
        (drop)="onDrop($event)"
      >
        <span class="icon">cloud_upload</span>
        Arraste arquivos aqui (PDF, imagem, áudio, Word, Excel; até {{ maxMb }} MB)
      </div>

      @if (uploading()) {
        <mat-progress-bar mode="determinate" [value]="progress()" />
      }
      @if (error(); as message) {
        <p class="error-text" role="alert">{{ message }}</p>
      }
      @if (loading() && docs().length === 0) {
        <mat-progress-bar mode="indeterminate" />
      }

      <ul class="docs__list">
        @for (d of docs(); track d.id) {
          <li class="doc">
            <span class="doc__icon"
              ><span class="icon">{{ icon(d) }}</span></span
            >
            <div class="doc__text">
              <button type="button" class="doc__name" (click)="open(d)">{{ d.name }}</button>
              <span class="muted small">
                {{ d.category_label }} · {{ size(d) }} · {{ d.created_at | date: 'dd/MM/yyyy' }}
                @if (d.source === 'WHATSAPP') {
                  · pelo WhatsApp
                  @if (d.conversation_id) {
                    (<a [routerLink]="['/inbox', d.conversation_id]">conversa</a>)
                  }
                } @else if (d.uploaded_by_name) {
                  · por {{ d.uploaded_by_name }}
                }
                @if (d.case_number && !caseId()) {
                  · <span class="mono">{{ d.case_number }}</span>
                }
              </span>
            </div>
            <button
              mat-icon-button
              type="button"
              [matMenuTriggerFor]="menu"
              [attr.aria-label]="'Ações de ' + d.name"
            >
              <span class="icon">more_vert</span>
            </button>
            <mat-menu #menu="matMenu">
              <button mat-menu-item type="button" (click)="open(d)">Abrir</button>
              <button mat-menu-item type="button" (click)="download(d)">Baixar</button>
              @for (c of categories; track c[0]) {
                @if (c[0] !== d.category) {
                  <button mat-menu-item type="button" (click)="recategorize(d, c[0])">
                    Marcar como: {{ c[1] }}
                  </button>
                }
              }
              @if (canDelete()) {
                <button mat-menu-item type="button" class="danger" (click)="remove(d)">
                  Apagar
                </button>
              }
            </mat-menu>
          </li>
        } @empty {
          @if (!loading()) {
            <li class="empty-state">
              <span class="icon">folder_off</span>
              Nenhum documento ainda. Envie aqui ou peça ao cliente pelo WhatsApp: o que ele mandar
              entra sozinho nesta pasta.
            </li>
          }
        }
      </ul>
    </section>
  `,
  styles: `
    .docs__category {
      width: 220px;
    }
    .docs__drop {
      margin-bottom: 12px;
      padding: 14px 16px;
      border: 1.5px dashed var(--mat-sys-outline);
      border-radius: var(--tm-radius-sm);
      color: var(--mat-sys-on-surface-variant);
      display: flex;
      align-items: center;
      gap: 8px;
      font: var(--mat-sys-body-small);
    }
    .docs__drop--over {
      border-color: var(--mat-sys-primary);
      background: var(--tm-info-soft);
    }
    .docs__list {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .doc {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 0;
    }
    .doc + .doc {
      border-top: 1px solid var(--mat-sys-outline-variant);
    }
    .doc__icon {
      flex: none;
      width: 36px;
      height: 36px;
      border-radius: var(--tm-radius-sm);
      display: grid;
      place-items: center;
      background: var(--tm-info-soft);
      color: var(--tm-info);
    }
    .doc__text {
      display: flex;
      flex-direction: column;
      gap: 2px;
      flex: 1;
      min-width: 0;
    }
    .doc__name {
      background: none;
      border: 0;
      padding: 0;
      text-align: left;
      font:
        600 14px / 1.4 Inter,
        system-ui,
        sans-serif;
      color: inherit;
      cursor: pointer;
      overflow-wrap: anywhere;
    }
    .doc__name:hover {
      color: var(--mat-sys-primary);
    }
    .danger {
      color: var(--tm-danger);
    }
    @media (max-width: 600px) {
      .docs__category {
        width: 100%;
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentsPanel {
  private readonly api = inject(DocumentsService);
  private readonly auth = inject(AuthService);
  private readonly snack = inject(MatSnackBar);

  readonly clientId = input<string | null>(null);
  readonly caseId = input<string | null>(null);

  readonly accepted = ACCEPTED_FILES;
  readonly maxMb = MAX_FILE_MB;
  readonly categories = (Object.entries(CATEGORY_LABELS) as [DocumentCategory, string][]).filter(
    ([key]) => key !== 'WHATSAPP',
  );
  readonly category = new FormControl<DocumentCategory>('OUTRO', { nonNullable: true });

  readonly docs = signal<DocumentItem[]>([]);
  readonly loading = signal(false);
  readonly uploading = signal(false);
  readonly progress = signal(0);
  readonly dragOver = signal(false);
  readonly error = signal<string | null>(null);
  readonly canDelete = computed(() => {
    const role = this.auth.session()?.role;
    return role === 'OWNER' || role === 'LAWYER';
  });

  constructor() {
    effect(() => {
      const client = this.clientId();
      const legalCase = this.caseId();
      untracked(() => this.load(client, legalCase));
    });
  }

  icon(d: DocumentItem): string {
    return fileIcon(d.content_type);
  }

  size(d: DocumentItem): string {
    return formatSize(d.size);
  }

  open(d: DocumentItem): void {
    this.api.open(d);
  }

  download(d: DocumentItem): void {
    this.api.download(d);
  }

  onFiles(picker: HTMLInputElement): void {
    const files = Array.from(picker.files ?? []);
    picker.value = '';
    this.uploadAll(files);
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragOver.set(true);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragOver.set(false);
    this.uploadAll(Array.from(event.dataTransfer?.files ?? []));
  }

  recategorize(d: DocumentItem, category: DocumentCategory): void {
    this.api.update(d.id, { category }).subscribe({
      next: (updated) => this.docs.update((list) => list.map((x) => (x.id === d.id ? updated : x))),
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }

  remove(d: DocumentItem): void {
    this.api.remove(d.id).subscribe({
      next: () => {
        this.docs.update((list) => list.filter((x) => x.id !== d.id));
        this.snack.open('Documento apagado.', 'OK', { duration: 3000 });
      },
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }

  private uploadAll(files: File[]): void {
    if (files.length === 0) return;
    const tooBig = files.find((f) => f.size > MAX_FILE_MB * 1024 * 1024);
    if (tooBig) {
      this.error.set(`"${tooBig.name}" passa de ${MAX_FILE_MB} MB.`);
      return;
    }
    this.error.set(null);
    this.uploadNext(files, 0);
  }

  private uploadNext(files: File[], index: number): void {
    if (index >= files.length) {
      this.uploading.set(false);
      return;
    }
    this.uploading.set(true);
    this.progress.set(0);
    this.api
      .upload({
        file: files[index],
        client_id: this.clientId(),
        legal_case_id: this.caseId(),
        category: this.category.value,
      })
      .subscribe({
        next: (event) => {
          if (event.type === HttpEventType.UploadProgress && event.total) {
            this.progress.set(Math.round((100 * event.loaded) / event.total));
          } else if (event.type === HttpEventType.Response && event.body) {
            const doc = event.body;
            this.docs.update((list) => [doc, ...list]);
            this.uploadNext(files, index + 1);
          }
        },
        error: (err: unknown) => {
          this.uploading.set(false);
          this.error.set(`${files[index].name}: ${toApiError(err).message}`);
        },
      });
  }

  private load(client: string | null, legalCase: string | null): void {
    if (!client && !legalCase) {
      this.docs.set([]);
      return;
    }
    this.loading.set(true);
    const filters = client ? { client } : { legal_case: legalCase ?? undefined };
    this.api.list(filters).subscribe({
      next: (page) => {
        this.loading.set(false);
        this.docs.set(page.results);
      },
      error: (err: unknown) => {
        this.loading.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
