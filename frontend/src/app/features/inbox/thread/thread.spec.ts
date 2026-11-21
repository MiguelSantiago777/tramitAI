import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { signal } from '@angular/core';

import { AuthService } from '../../../core/auth/auth.service';
import { DraftsService } from '../../aprovacoes/drafts.service';
import { DocumentsService } from '../../../shared/documents/documents.service';
import { TenantService } from '../../../core/tenant/tenant.service';
import { ClientsService } from '../../clientes/clients.service';
import { Conversation, Message } from '../inbox.models';
import { InboxService } from '../inbox.service';
import { Thread } from './thread';

const conversation: Conversation = {
  id: 'conv1',
  wa_id: '5521998765432',
  phone: '+5521998765432',
  contact_name: 'Maria',
  client_id: null,
  client_name: '',
  suggested_client_id: null,
  suggested_client_name: '',
  pending_drafts: 0,
  assignee_id: null,
  assignee_name: '',
  ai_consent_version: null,
  ai_failed_at: null,
  status: 'OPEN',
  last_inbound_at: '2026-11-17T10:00:00Z',
  last_message_at: '2026-11-17T10:05:00Z',
  unread_count: 0,
  window_open: true,
  window_expires_at: '2026-11-18T10:00:00Z',
  last_message: null,
};

function msg(id: string, direction: 'IN' | 'OUT', body: string, extra: Partial<Message> = {}) {
  return {
    id,
    direction,
    type: 'text',
    body,
    status: direction === 'IN' ? 'RECEIVED' : 'SENT',
    error_detail: '',
    sent_by_name: direction === 'OUT' ? 'Dra. Ana' : '',
    wa_timestamp: null,
    delivered_at: null,
    read_at: null,
    created_at: '2026-11-17T10:00:00Z',
    ...extra,
  } as Message;
}

describe('Thread', () => {
  let fixture: ComponentFixture<Thread>;
  let inbox: Record<string, ReturnType<typeof vi.fn>>;

  async function setup(conv: Conversation, newestFirst: Message[]) {
    inbox = {
      get: vi.fn(() => of(conv)),
      messages: vi.fn(() =>
        of({ count: newestFirst.length, next: null, previous: null, results: newestFirst }),
      ),
      markRead: vi.fn(() => of(undefined)),
      send: vi.fn(),
      sendAttachment: vi.fn(),
      update: vi.fn(),
      retryAi: vi.fn(() => of(undefined)),
    };
    await TestBed.configureTestingModule({
      imports: [Thread],
      providers: [
        provideRouter([]),
        { provide: InboxService, useValue: inbox },
        { provide: TenantService, useValue: { members: () => of([]) } },
        { provide: ClientsService, useValue: { list: vi.fn(() => of({ results: [] })) } },
        {
          provide: DraftsService,
          useValue: {
            list: vi.fn(() => of({ count: 0, next: null, previous: null, results: [] })),
          },
        },
        { provide: AuthService, useValue: { session: signal({ can_approve: true }) } },
        { provide: DocumentsService, useValue: { objectUrl: vi.fn(), open: vi.fn() } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(Thread);
    fixture.componentRef.setInput('conversationId', conv.id);
    await fixture.whenStable();
  }

  const el = () => fixture.nativeElement as HTMLElement;

  afterEach(() => fixture?.destroy());

  it('mostra as mensagens em ordem cronológica e marca como lida', async () => {
    await setup(conversation, [msg('2', 'OUT', 'Vou verificar.'), msg('1', 'IN', 'Bom dia')]);

    const bodies = [...el().querySelectorAll('.bubble__body')].map((b) => b.textContent);
    expect(bodies).toEqual(['Bom dia', 'Vou verificar.']);
    expect(el().textContent).toContain('Enviada ✓');
    expect(inbox['markRead']).toHaveBeenCalledWith('conv1');
  });

  it('avisa quando a Vera desistiu e pede para tentar de novo', async () => {
    await setup({ ...conversation, ai_failed_at: '2026-11-18T11:05:00Z' }, [msg('1', 'IN', 'Olá')]);
    expect(el().textContent).toContain('A Vera não conseguiu responder');
    const button = [...el().querySelectorAll('.thread__ai-failed button')][0] as HTMLButtonElement;
    button.click();
    await fixture.whenStable();
    expect(inbox['retryAi']).toHaveBeenCalledWith('conv1');
    expect(el().textContent).toContain('A Vera está tentando de novo');
  });

  it('envia a resposta e acrescenta na conversa', async () => {
    await setup(conversation, [msg('1', 'IN', 'Bom dia')]);
    inbox['send'].mockReturnValue(of(msg('9', 'OUT', 'Olá!', { status: 'QUEUED' })));

    fixture.componentInstance.draft.setValue('  Olá!  ');
    fixture.componentInstance.send();
    await fixture.whenStable();

    expect(inbox['send']).toHaveBeenCalledWith('conv1', 'Olá!');
    expect(fixture.componentInstance.messages().map((m) => m.id)).toEqual(['1', '9']);
    expect(el().textContent).toContain('Enviando…');
    expect(fixture.componentInstance.draft.value).toBe('');
  });

  it('anexa um arquivo e envia com o texto como legenda', async () => {
    await setup(conversation, [msg('1', 'IN', 'Bom dia')]);
    const doc = { id: 'd1', name: 'procuracao.pdf', content_type: 'application/pdf', size: 20 };
    inbox['sendAttachment'].mockReturnValue(
      of(
        msg('9', 'OUT', 'Segue', {
          type: 'document',
          status: 'QUEUED',
          document: doc,
          media_pending: false,
        }),
      ),
    );

    const file = new File(['%PDF-1.4'], 'procuracao.pdf', { type: 'application/pdf' });
    const picker = el().querySelector('[data-testid="file-picker"]') as HTMLInputElement;
    Object.defineProperty(picker, 'files', { value: [file], configurable: true });
    picker.dispatchEvent(new Event('change'));
    await fixture.whenStable();

    expect(el().querySelector('[data-testid="attachment"]')?.textContent).toContain(
      'procuracao.pdf',
    );
    expect(fixture.componentInstance.canSend()).toBe(true);

    fixture.componentInstance.draft.setValue(' Segue ');
    fixture.componentInstance.send();
    await fixture.whenStable();

    expect(inbox['sendAttachment']).toHaveBeenCalledWith('conv1', file, 'Segue');
    expect(inbox['send']).not.toHaveBeenCalled();
    expect(fixture.componentInstance.attachment()).toBeNull();
    expect(el().querySelector('[data-testid="attachment"]')).toBeNull();
    expect(el().textContent).toContain('procuracao.pdf');
  });

  it('esconde o campo de resposta quando a janela de 24h está fechada', async () => {
    await setup({ ...conversation, window_open: false }, [msg('1', 'IN', 'Oi')]);
    expect(el().querySelector('[data-testid="window-closed"]')).not.toBeNull();
    expect(el().querySelector('textarea')).toBeNull();
  });

  it('mostra o erro do backend ao enviar', async () => {
    await setup(conversation, []);
    inbox['send'].mockReturnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 409,
            error: {
              error: {
                code: 'window_closed',
                message: 'A janela de 24h do WhatsApp está fechada.',
              },
            },
          }),
      ),
    );
    fixture.componentInstance.draft.setValue('Oi');
    fixture.componentInstance.send();
    await fixture.whenStable();
    expect(el().textContent).toContain('A janela de 24h do WhatsApp está fechada.');
  });

  it('mostra o motivo de falha do envio', async () => {
    await setup(conversation, [
      msg('2', 'OUT', 'Oi', { status: 'FAILED', error_detail: 'Número sem WhatsApp' }),
    ]);
    expect(el().querySelector('.bubble__error')?.textContent).toContain('Número sem WhatsApp');
  });
});
