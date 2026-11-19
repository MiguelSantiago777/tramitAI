import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { of } from 'rxjs';

import { AuthService } from '../../../core/auth/auth.service';
import { TeamMember, TenantService } from '../../../core/tenant/tenant.service';
import { Team } from './team';

const me: TeamMember = {
  id: 'm1',
  user_id: 'u1',
  email: 'titular@escritorio.com',
  full_name: 'Ana Titular',
  role: 'OWNER',
  is_active: true,
  pending: false,
  is_me: true,
};
const invited: TeamMember = {
  id: 'm2',
  user_id: 'u2',
  email: 'nova@escritorio.com',
  full_name: '',
  role: 'LAWYER',
  is_active: true,
  pending: true,
  is_me: false,
};

describe('Team', () => {
  let fixture: ComponentFixture<Team>;
  let api: Record<string, ReturnType<typeof vi.fn>>;
  let dialog: { open: ReturnType<typeof vi.fn> };

  async function setup(role: 'OWNER' | 'LAWYER') {
    dialog = { open: vi.fn() };
    api = {
      team: vi.fn(() => of([me, invited])),
      invite: vi.fn(() => of({ ...invited, access_link: 'https://app/convite' })),
      updateMember: vi.fn(() => of(invited)),
      accessLink: vi.fn(() =>
        of({ url: 'https://app/redefinir-senha?uid=x&token=y', kind: 'invite' }),
      ),
    };
    await TestBed.configureTestingModule({
      imports: [Team],
      providers: [
        { provide: TenantService, useValue: api },
        { provide: AuthService, useValue: { session: signal({ role }) } },
        { provide: MatDialog, useValue: dialog },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(Team);
    await fixture.whenStable();
  }

  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';

  it('lista a equipe com convite pendente e marca você', async () => {
    await setup('OWNER');
    expect(text()).toContain('Ana Titular (você)');
    expect(text()).toContain('Convite pendente');
    expect(text()).toContain('Advogado(a)');
  });

  it('titular convida', async () => {
    await setup('OWNER');
    fixture.componentInstance.inviting.set(true);
    fixture.componentInstance.form.setValue({
      email: 'nova@escritorio.com',
      full_name: 'Nova',
      role: 'STAFF',
    });
    fixture.componentInstance.invite();
    expect(api['invite']).toHaveBeenCalledWith({
      email: 'nova@escritorio.com',
      full_name: 'Nova',
      role: 'STAFF',
    });
    // Sem e-mail: o titular recebe o link para mandar.
    expect(dialog.open.mock.calls[0][1].data).toEqual(
      expect.objectContaining({ url: 'https://app/convite', kind: 'invite' }),
    );
  });

  it('gera link de nova senha pelo menu', async () => {
    await setup('OWNER');
    fixture.componentInstance.link(invited);
    expect(api['accessLink']).toHaveBeenCalledWith('m2');
    expect(dialog.open.mock.calls[0][1].data.email).toBe('nova@escritorio.com');
  });

  it('quem não é titular só vê a lista', async () => {
    await setup('LAWYER');
    const buttons = [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')];
    expect(buttons.some((b) => b.textContent?.includes('Convidar'))).toBe(false);
    expect(buttons.some((b) => b.getAttribute('aria-label') === 'Opções')).toBe(false);
  });
});
