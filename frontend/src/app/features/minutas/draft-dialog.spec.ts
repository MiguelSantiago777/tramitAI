import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA } from '@angular/material/dialog';
import { of } from 'rxjs';

import { DocumentsService } from '../../shared/documents/documents.service';
import { FinanceiroService } from '../financeiro/financeiro.service';
import { DraftDialog } from './draft-dialog';
import { DocumentDraft, DraftsService } from './drafts.service';

const pending: DocumentDraft = {
  id: 'd1',
  kind: 'POWER',
  kind_label: 'Procuração',
  title: 'Procuração',
  client_id: 'c1',
  legal_case_id: null,
  fee_agreement_id: null,
  status: 'PENDING',
  error_code: '',
  review_notes: '',
  missing_fields: [],
  docx_id: null,
  pdf_id: null,
  created_at: '',
};

describe('DraftDialog', () => {
  let fixture: ComponentFixture<DraftDialog>;
  let api: { create: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> };
  let documents: { download: ReturnType<typeof vi.fn> };

  beforeEach(async () => {
    vi.useFakeTimers();
    api = {
      create: vi.fn(() => of(pending)),
      get: vi.fn(() =>
        of({
          ...pending,
          status: 'DONE',
          docx_id: 'w1',
          pdf_id: 'p1',
          missing_fields: ['[ENDEREÇO DO CLIENTE]'],
          review_notes: 'Confira o endereço.',
        }),
      ),
    };
    documents = { download: vi.fn() };
    await TestBed.configureTestingModule({
      imports: [DraftDialog],
      providers: [
        { provide: MAT_DIALOG_DATA, useValue: { clientId: 'c1', label: 'Maria' } },
        { provide: DraftsService, useValue: api },
        { provide: DocumentsService, useValue: documents },
        { provide: FinanceiroService, useValue: { agreements: () => of({ results: [] }) } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(DraftDialog);
    fixture.detectChanges();
  });

  afterEach(() => vi.useRealTimers());

  const el = () => fixture.nativeElement as HTMLElement;
  const button = (label: string) =>
    [...el().querySelectorAll('button')].find((b) => b.textContent?.includes(label));

  it('pede título e texto antes de chamar a Vera', () => {
    button('Escrever')?.click();
    fixture.detectChanges();
    expect(api.create).not.toHaveBeenCalled();
    expect(el().textContent).toContain('Preencha o título');
  });

  it('cria, espera ficar pronta e oferece Word e PDF', () => {
    fixture.componentInstance.kind.setValue('POWER');
    fixture.componentInstance.title.setValue('Procuração');
    fixture.componentInstance.instructions.setValue('Poderes para receber e dar quitação.');
    button('Escrever')?.click();
    expect(api.create).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'POWER', client_id: 'c1', fee_agreement_id: null }),
    );
    fixture.detectChanges();
    expect(el().textContent).toContain('A Vera está escrevendo');

    vi.advanceTimersByTime(3000);
    fixture.detectChanges();
    expect(el().textContent).toContain('[ENDEREÇO DO CLIENTE]');
    expect(el().textContent).toContain('Confira o endereço.');
    button('Baixar Word')?.click();
    expect(documents.download).toHaveBeenCalledWith({ id: 'w1', name: 'Procuração.docx' });
  });
});
