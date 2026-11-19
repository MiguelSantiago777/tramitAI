import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA } from '@angular/material/dialog';

import { AccessLinkDialog } from './access-link-dialog';

describe('AccessLinkDialog', () => {
  it('mostra o link e monta a mensagem do WhatsApp', async () => {
    await TestBed.configureTestingModule({
      imports: [AccessLinkDialog],
      providers: [
        {
          provide: MAT_DIALOG_DATA,
          useValue: {
            url: 'https://app.tramitai.pro/redefinir-senha?uid=a&token=b&convite=1',
            kind: 'invite',
            name: 'Nova Advogada',
            email: 'nova@x.com',
            officeName: 'Escritório A',
          },
        },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(AccessLinkDialog);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[data-testid="access-link"]')?.textContent).toContain('convite=1');
    const href = decodeURIComponent(el.querySelector('a')?.getAttribute('href') ?? '');
    expect(href).toContain('Olá, Nova!');
    expect(href).toContain('Escritório A');
    expect(href).toContain('nova@x.com');
  });
});
