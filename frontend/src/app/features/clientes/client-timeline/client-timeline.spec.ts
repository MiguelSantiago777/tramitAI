import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { Timeline } from '../client.models';
import { ClientsService } from '../clients.service';
import { ClientTimeline } from './client-timeline';

const page: Timeline = {
  results: [
    {
      id: 'n1',
      type: 'note',
      at: '2026-11-17T13:00:00Z',
      title: 'Ligação',
      body: 'Expliquei a conclusão.',
      meta: { author: 'Dra. Ana', case_number: '0801234-39.2024.8.19.0001', case_id: 'p1' },
    },
    {
      id: 'm1',
      type: 'message',
      at: '2026-11-17T12:00:00Z',
      title: 'Cliente escreveu',
      body: 'Tem novidade?',
      meta: { conversation_id: 'c1', direction: 'IN' },
    },
  ],
  next_before: '2026-11-17T12:00:00Z',
};

describe('ClientTimeline', () => {
  let fixture: ComponentFixture<ClientTimeline>;
  let api: { timeline: ReturnType<typeof vi.fn>; addNote: ReturnType<typeof vi.fn> };
  let open: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    api = {
      timeline: vi.fn(() => of(page)),
      addNote: vi.fn(() => of({})),
    };
    open = vi.fn(() => ({ afterClosed: () => of(undefined) }));
    await TestBed.configureTestingModule({
      imports: [ClientTimeline],
      providers: [
        provideRouter([]),
        { provide: ClientsService, useValue: api },
        { provide: MatDialog, useValue: { open } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ClientTimeline);
    fixture.componentRef.setInput('clientId', 'cl1');
    fixture.componentRef.setInput('clientName', 'Maria da Silva');
    await fixture.whenStable();
  });

  const el = () => fixture.nativeElement as HTMLElement;

  it('mostra o histórico com autor, processo e link da conversa', () => {
    expect(api.timeline).toHaveBeenCalledWith('cl1', null);
    expect(el().textContent).toContain('Expliquei a conclusão.');
    expect(el().textContent).toContain('por Dra. Ana');
    expect(el().textContent).toContain('0801234-39.2024.8.19.0001');
    expect(el().textContent).toContain('Abrir conversa');
  });

  it('registra atendimento e recarrega', async () => {
    fixture.componentInstance.kind.setValue('MEETING');
    fixture.componentInstance.body.setValue('  Reunião sobre documentos.  ');
    fixture.componentInstance.addNote();
    await fixture.whenStable();
    expect(api.addNote).toHaveBeenCalledWith('cl1', {
      kind: 'MEETING',
      body: 'Reunião sobre documentos.',
    });
    expect(api.timeline).toHaveBeenCalledTimes(2);
  });

  it('não registra texto vazio', () => {
    fixture.componentInstance.body.setValue('   ');
    fixture.componentInstance.addNote();
    expect(api.addNote).not.toHaveBeenCalled();
  });

  it('ver mais antigos pede a página seguinte', () => {
    fixture.componentInstance.more();
    expect(api.timeline).toHaveBeenLastCalledWith('cl1', '2026-11-17T12:00:00Z');
  });

  it('nova tarefa já vem com o cliente', () => {
    fixture.componentInstance.newTask();
    const [, config] = open.mock.calls[0] as [unknown, { data: { defaults: { client: unknown } } }];
    expect(config.data.defaults.client).toEqual({ id: 'cl1', name: 'Maria da Silva' });
  });
});
