import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { Conversation } from '../inbox.models';
import { InboxService } from '../inbox.service';
import { Inbox } from './inbox';

const base: Conversation = {
  id: 'c1',
  wa_id: '5521998765432',
  phone: '+5521998765432',
  contact_name: 'Maria (perfil)',
  client_id: 'cl1',
  client_name: 'Maria da Silva',
  suggested_client_id: null,
  suggested_client_name: '',
  pending_drafts: 1,
  assignee_id: null,
  assignee_name: '',
  ai_consent_version: 1,
  status: 'OPEN',
  last_inbound_at: null,
  last_message_at: '2026-11-17T10:00:00Z',
  unread_count: 2,
  window_open: true,
  window_expires_at: null,
  last_message: { direction: 'IN', type: 'text', status: 'RECEIVED', preview: 'Tem novidade?' },
};

describe('Inbox', () => {
  it('lista conversas com nome do cliente, prévia, não lidas e alerta de sem vínculo', async () => {
    const list = vi.fn(() =>
      of({
        count: 2,
        next: null,
        previous: null,
        results: [
          base,
          {
            ...base,
            id: 'c2',
            client_id: null,
            client_name: '',
            contact_name: '',
            phone: '+5521911112222',
            unread_count: 0,
          },
        ],
      }),
    );
    await TestBed.configureTestingModule({
      imports: [Inbox],
      providers: [provideRouter([]), { provide: InboxService, useValue: { list } }],
    }).compileComponents();

    const fixture = TestBed.createComponent(Inbox);
    await fixture.whenStable();
    const items = [...(fixture.nativeElement as HTMLElement).querySelectorAll('.inbox__item')];

    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('Maria da Silva');
    expect(items[0].textContent).toContain('Tem novidade?');
    expect(items[0].querySelector('.inbox__badge')?.textContent?.trim()).toBe('2');
    expect(items[1].textContent).toContain('(21) 91111-2222');
    expect(items[1].textContent).toContain('Sem cliente vinculado');
    expect(items[0].textContent).toContain('Rascunho aguardando aprovação');

    fixture.componentInstance.filter.setValue('unread');
    expect(list).toHaveBeenLastCalledWith({ q: '', unread: true, status: 'OPEN', assignee: '' });
    fixture.destroy();
  });
});
