import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { Task, isoDate } from '../agenda.models';
import { AgendaService } from '../agenda.service';
import { TaskItem } from './task-item';

function daysFromToday(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return isoDate(d);
}

const base: Task = {
  id: 't1',
  title: 'Verificar prazo: Intimação',
  description: '',
  kind: 'DEADLINE',
  status: 'OPEN',
  priority: 'HIGH',
  due_date: daysFromToday(0),
  due_time: null,
  assignee_id: 'u1',
  assignee_name: 'Dra. Ana',
  client_id: 'c1',
  client_name: 'Maria da Silva',
  legal_case_id: 'p1',
  case_number: '0801234-39.2024.8.19.0001',
  source: 'MOVEMENT',
  completed_at: null,
  completed_by_name: '',
  created_at: '',
  updated_at: '',
};

describe('TaskItem', () => {
  let fixture: ComponentFixture<TaskItem>;
  let api: { completeTask: ReturnType<typeof vi.fn>; reopenTask: ReturnType<typeof vi.fn> };

  async function setup(task: Partial<Task> = {}) {
    api = {
      completeTask: vi.fn(() => of({ ...base, ...task, status: 'DONE' })),
      reopenTask: vi.fn(() => of({ ...base, ...task, status: 'OPEN' })),
    };
    await TestBed.configureTestingModule({
      imports: [TaskItem],
      providers: [provideRouter([]), { provide: AgendaService, useValue: api }],
    }).compileComponents();
    fixture = TestBed.createComponent(TaskItem);
    fixture.componentRef.setInput('task', { ...base, ...task });
    await fixture.whenStable();
  }

  const el = () => fixture.nativeElement as HTMLElement;

  it('mostra prazo, prioridade, data, cliente e processo', async () => {
    await setup();
    expect(el().textContent).toContain('Prazo');
    expect(el().textContent).toContain('Alta');
    expect(el().textContent).toContain('Hoje');
    expect(el().textContent).toContain('Maria da Silva');
    expect(el().textContent).toContain('0801234-39.2024.8.19.0001');
  });

  it('marca atrasada em vermelho', async () => {
    await setup({ due_date: daysFromToday(-3) });
    expect(el().querySelector('.task--overdue')).not.toBeNull();
  });

  it('concluir pelo checkbox chama a API e avisa o pai', async () => {
    await setup();
    const changed = vi.fn();
    fixture.componentInstance.changed.subscribe(changed);
    (el().querySelector('input[type=checkbox]') as HTMLInputElement).click();
    expect(api.completeTask).toHaveBeenCalledWith('t1');
    expect(changed).toHaveBeenCalledWith(expect.objectContaining({ status: 'DONE' }));
  });

  it('desmarcar uma concluída reabre', async () => {
    await setup({ status: 'DONE', completed_at: '2026-11-17T10:00:00Z' });
    (el().querySelector('input[type=checkbox]') as HTMLInputElement).click();
    expect(api.reopenTask).toHaveBeenCalledWith('t1');
  });
});
