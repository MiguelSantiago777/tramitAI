import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar } from '@angular/material/snack-bar';

import { AuthService } from '../../../core/auth/auth.service';
import { toApiError } from '../../../core/http/api-error';
import { TenantService, TermVersion } from '../../../core/tenant/tenant.service';

/** Termo de ciência de uso de IA que o cliente final aceita. Só o titular publica. */
@Component({
  selector: 'app-term-settings',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    MatButtonModule,
    MatExpansionModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  template: `
    <header class="page-header">
      <div>
        <h1>Termo de ciência de IA</h1>
        <p>
          Texto que o cliente aceita antes de conversar com a Vera. Editar publica uma nova versão;
          os aceites antigos continuam ligados à versão que o cliente viu.
        </p>
      </div>
    </header>

    @if (error(); as message) {
      <p class="error-text" role="alert">{{ message }}</p>
    }

    <section class="form-card">
      @if (active(); as term) {
        <h2>Versão {{ term.version }} (vigente)</h2>
        <p class="muted small">
          Publicada em {{ term.created_at | date: 'dd/MM/yyyy HH:mm' }}
          @if (term.created_by_name) {
            por {{ term.created_by_name }}
          }
        </p>
      } @else if (loaded()) {
        <h2>Nenhum termo publicado</h2>
        <p class="muted small">Publique o termo antes de começar o atendimento com IA.</p>
      }

      @if (isOwner()) {
        <mat-form-field appearance="outline" class="full">
          <mat-label>Texto do termo</mat-label>
          <textarea matInput [formControl]="body" rows="18"></textarea>
          @if (body.hasError('required')) {
            <mat-error>O termo não pode ficar vazio.</mat-error>
          }
        </mat-form-field>
        <div class="form-actions">
          <button
            mat-flat-button
            type="button"
            [disabled]="saving() || body.pristine"
            (click)="publish()"
          >
            Publicar nova versão
          </button>
        </div>
      } @else {
        @if (active(); as term) {
          <pre class="term-text">{{ term.body }}</pre>
        }
        <p class="muted small">Só o titular do escritório pode alterar o termo.</p>
      }
    </section>

    @if (history().length > 0) {
      <mat-accordion>
        <mat-expansion-panel>
          <mat-expansion-panel-header>
            <mat-panel-title>Versões anteriores ({{ history().length }})</mat-panel-title>
          </mat-expansion-panel-header>
          @for (v of history(); track v.id) {
            <h3>Versão {{ v.version }} · {{ v.created_at | date: 'dd/MM/yyyy' }}</h3>
            <pre class="term-text">{{ v.body }}</pre>
          }
        </mat-expansion-panel>
      </mat-accordion>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TermSettings {
  private readonly tenant = inject(TenantService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly auth = inject(AuthService);

  readonly isOwner = computed(() => this.auth.session()?.role === 'OWNER');
  readonly body = new FormControl('', { nonNullable: true, validators: Validators.required });
  readonly versions = signal<TermVersion[]>([]);
  readonly active = computed(() => this.versions().find((v) => v.is_active) ?? null);
  readonly history = computed(() => this.versions().filter((v) => !v.is_active));
  readonly saving = signal(false);
  readonly loaded = signal(false);
  readonly error = signal<string | null>(null);

  constructor() {
    this.load();
  }

  publish(): void {
    if (this.body.invalid) {
      this.body.markAsTouched();
      return;
    }
    this.saving.set(true);
    this.error.set(null);
    this.tenant.publishTerm(this.body.value).subscribe({
      next: () => {
        this.saving.set(false);
        this.snackBar.open('Nova versão publicada.', undefined, { duration: 3000 });
        this.load();
      },
      error: (err: unknown) => {
        this.saving.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  private load(): void {
    this.tenant.termVersions().subscribe({
      next: (versions) => {
        this.versions.set(versions);
        this.loaded.set(true);
        this.body.reset(versions.find((v) => v.is_active)?.body ?? '');
      },
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }
}
