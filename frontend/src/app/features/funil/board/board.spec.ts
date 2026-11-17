import { CdkDragDrop } from '@angular/cdk/drag-drop';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { of } from 'rxjs';

import { Opportunity, Stage } from '../funil.models';
import { FunilService } from '../funil.service';
import { Board } from './board';

function opp(
  id: string,
  stage: Stage,
  position: number,
  extra: Partial<Opportunity> = {},
): Opportunity {
  return {
    id,
    title: `Caso ${id}`,
    client_id: `c${id}`,
    client_name: `Cliente ${id}`,
    client_phone: '',
    client_status: 'LEAD',
    stage,
    area: 'TRABALHISTA',
    source: 'WHATSAPP',
    estimated_value: '2000.00',
    owner_id: null,
    owner_name: '',
    conversation_id: null,
    notes: '',
    lost_reason: '',
    position,
    stage_changed_at: new Date().toISOString(),
    closed_at: null,
    created_at: '',
    updated_at: '',
    ...extra,
  };
}

describe('Board', () => {
  let fixture: ComponentFixture<Board>;
  let api: Record<string, ReturnType<typeof vi.fn>>;
  let dialogResult: unknown;
  let open: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    api = {
      board: vi.fn(() => of([opp('1', 'NEW', 0), opp('2', 'NEW', 1), opp('3', 'CONSULT', 0)])),
      summary: vi.fn(() =>
        of({
          open_count: 3,
          by_stage: { NEW: 2, TRIAGE: 0, CONSULT: 1, PROPOSAL: 0 },
          open_value: '6000.00',
          won_count: 1,
          lost_count: 1,
          won_value: '3000.00',
          conversion_rate: 0.5,
          period_days: 90,
        }),
      ),
      move: vi.fn(() => of(opp('1', 'CONSULT', 0))),
    };
    dialogResult = undefined;
    open = vi.fn(() => ({ afterClosed: () => of(dialogResult) }));
    await TestBed.configureTestingModule({
      imports: [Board],
      providers: [
        { provide: FunilService, useValue: api },
        { provide: MatDialog, useValue: { open } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(Board);
    await fixture.whenStable();
  });

  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';
  const column = (stage: Stage) => fixture.componentInstance.columns().find((c) => c.id === stage)!;

  function dropEvent(from: Stage, fromIndex: number, to: Stage, toIndex: number) {
    const source = { data: column(from).items };
    const target = from === to ? source : { data: column(to).items };
    return {
      previousContainer: source,
      container: target,
      previousIndex: fromIndex,
      currentIndex: toIndex,
    } as unknown as CdkDragDrop<Opportunity[]>;
  }

  it('monta as colunas, os números e o valor por coluna', () => {
    expect(column('NEW').items.map((o) => o.id)).toEqual(['1', '2']);
    expect(text()).toContain('em negociação');
    expect(text()).toContain('50%');
    expect(text()).toContain('Cliente 3');
    expect(fixture.componentInstance.columnValue(column('NEW'))).toContain('4.000');
  });

  it('arrastar para outra etapa salva etapa e posição', () => {
    fixture.componentInstance.drop(dropEvent('NEW', 0, 'CONSULT', 0), 'CONSULT');
    expect(api['move']).toHaveBeenCalledWith('1', 'CONSULT', 0, '');
    expect(api['board']).toHaveBeenCalledTimes(2); // recarrega do servidor depois de salvar
  });

  it('não contratou pede o motivo antes de salvar', () => {
    dialogResult = 'Achou caro';
    fixture.componentInstance.drop(dropEvent('NEW', 0, 'LOST', 0), 'LOST');
    expect(open).toHaveBeenCalled();
    expect(api['move']).toHaveBeenCalledWith('1', 'LOST', 0, 'Achou caro');
  });

  it('desistir do motivo não move e recarrega o quadro', () => {
    dialogResult = undefined;
    fixture.componentInstance.drop(dropEvent('NEW', 0, 'LOST', 0), 'LOST');
    expect(api['move']).not.toHaveBeenCalled();
    expect(api['board']).toHaveBeenCalledTimes(2);
  });
});
