import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { CalendarEvent, isoDate } from '../agenda.models';
import { AgendaService } from '../agenda.service';
import { AgendaPage } from './agenda-page';

function todayAt(hour: number): string {
  const d = new Date();
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
}

const hearing: CalendarEvent = {
  id: 'e1',
  title: 'Audiência de conciliação',
  kind: 'HEARING',
  status: 'SCHEDULED',
  starts_at: todayAt(14),
  ends_at: null,
  location: 'Fórum de Nova Iguaçu',
  notes: '',
  responsible_id: null,
  responsible_name: '',
  client_id: 'c1',
  client_name: 'Maria da Silva',
  legal_case_id: null,
  case_number: '',
  remind_client: true,
  client_reminded_at: null,
  created_at: '',
  updated_at: '',
};

describe('AgendaPage', () => {
  let fixture: ComponentFixture<AgendaPage>;
  let events: ReturnType<typeof vi.fn>;
  let open: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    events = vi.fn(() => of({ count: 1, next: null, previous: null, results: [hearing] }));
    open = vi.fn(() => ({ afterClosed: () => of(undefined) }));
    await TestBed.configureTestingModule({
      imports: [AgendaPage],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AgendaService, useValue: { events } },
        { provide: MatDialog, useValue: { open } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(AgendaPage);
    await fixture.whenStable();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  // Buscas da semana na tela (a outra busca é a das pré-reservas dos próximos 30 dias).
  const weekCalls = () =>
    (events.mock.calls as [{ start: string; end: string }][])
      .map(([f]) => f)
      .filter((f) => (Date.parse(f.end) - Date.parse(f.start)) / 86_400_000 === 6);

  it('busca a semana atual (segunda a domingo) e põe o compromisso no dia certo', () => {
    const [filters] = weekCalls();
    const start = new Date(`${filters.start}T00:00:00`);
    expect(start.getDay()).toBe(1); // segunda
    const today = el().querySelector('.day--today');
    expect(today?.textContent).toContain('Audiência de conciliação');
    expect(today?.textContent).toContain('Maria da Silva');
    expect(today?.textContent).toContain('Lembrete na véspera');
    expect(el().querySelectorAll('.day')).toHaveLength(7);
  });

  it('navega para a próxima semana', () => {
    const next = el().querySelector('button[aria-label="Próxima semana"]') as HTMLButtonElement;
    next.click();
    const filters = weekCalls()[1];
    const monday = new Date();
    monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7) + 7);
    expect(filters.start).toBe(isoDate(monday));
  });

  it('clicar no + de um dia abre o compromisso já com a data', () => {
    const plus = el().querySelector('.day__add') as HTMLButtonElement;
    plus.click();
    const [, config] = open.mock.calls[0] as [unknown, { data: { defaults: { date: string } } }];
    expect(config.data.defaults.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
