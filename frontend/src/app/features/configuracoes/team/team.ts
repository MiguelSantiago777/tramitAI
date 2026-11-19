import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Observable } from 'rxjs';

import { ROLE_LABELS, Role } from '../../../core/auth/auth.models';
import { AuthService } from '../../../core/auth/auth.service';
import { toApiError } from '../../../core/http/api-error';
import { TeamMember, TenantService } from '../../../core/tenant/tenant.service';
import { initialsOf } from '../../../shared/initials';
import { AccessLinkData, AccessLinkDialog } from './access-link-dialog';

/** Equipe do escritório: convidar, mudar papel, desativar. Mexer: só o titular. */
@Component({
  selector: 'app-team',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatMenuModule,
    MatSelectModule,
  ],
  templateUrl: './team.html',
  styleUrl: './team.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Team {
  private readonly api = inject(TenantService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly dialog = inject(MatDialog);
  private readonly session = inject(AuthService).session;
  readonly isOwner = computed(() => this.session()?.role === 'OWNER');

  readonly roles = Object.entries(ROLE_LABELS) as [Role, string][];
  readonly roleLabels = ROLE_LABELS;
  readonly members = signal<TeamMember[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly inviting = signal(false);

  readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
    full_name: [''],
    role: ['LAWYER' as Role],
  });

  readonly active = computed(() => this.members().filter((m) => m.is_active));
  readonly inactive = computed(() => this.members().filter((m) => !m.is_active));

  constructor() {
    this.load();
  }

  initials(m: TeamMember): string {
    return initialsOf(m.full_name || m.email);
  }

  invite(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.run(this.api.invite(this.form.getRawValue()), (member) => {
      this.form.reset({ email: '', full_name: '', role: 'LAWYER' });
      this.inviting.set(false);
      if (member.access_link) {
        this.showLink(member, member.access_link, 'invite');
      } else {
        this.snackBar.open('Pessoa adicionada à equipe.', undefined, { duration: 4000 });
      }
    });
  }

  setRole(m: TeamMember, role: Role): void {
    this.run(this.api.updateMember(m.id, { role }));
  }

  setActive(m: TeamMember, isActive: boolean): void {
    this.run(this.api.updateMember(m.id, { is_active: isActive }), () =>
      this.snackBar.open(isActive ? 'Acesso reativado.' : 'Acesso removido.', undefined, {
        duration: 3000,
      }),
    );
  }

  link(m: TeamMember): void {
    this.busy.set(true);
    this.error.set(null);
    this.api.accessLink(m.id).subscribe({
      next: ({ url, kind }) => {
        this.busy.set(false);
        this.showLink(m, url, kind);
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  private showLink(m: TeamMember, url: string, kind: 'invite' | 'reset'): void {
    this.dialog.open<AccessLinkDialog, AccessLinkData>(AccessLinkDialog, {
      data: {
        url,
        kind,
        name: m.full_name,
        email: m.email,
        officeName: this.session()?.tenant?.name ?? '',
      },
      maxWidth: '560px',
    });
  }

  private run<T>(request: Observable<T>, done?: (result: T) => void): void {
    this.busy.set(true);
    this.error.set(null);
    request.subscribe({
      next: (result) => {
        this.busy.set(false);
        done?.(result);
        this.load();
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }

  private load(): void {
    this.api.team().subscribe({
      next: (list) => this.members.set(list),
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }
}
