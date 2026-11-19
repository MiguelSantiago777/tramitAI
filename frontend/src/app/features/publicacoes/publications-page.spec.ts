import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { MonitoredOab, Publication } from './publication.models';
import { PublicationsPage } from './publications-page';
import { PublicationsService } from './publications.service';

const oab: MonitoredOab = {
  id: 'o1',
  number: '123456',
  uf: 'SP',
  lawyer_name: 'Dra. Ana',
  user_id: null,
  user_name: '',
  is_active: true,
  last_checked_at: '2026-11-19T12:00:00Z',
  fetched_until: '2026-11-19',
  last_error: '',
  new_count: 1,
  total_count: 5,
  discovering: false,
  discovered_at: '2026-11-19T12:00:00Z',
  created_at: '',
};

const pub: Publication = {
  id: 'p1',
  djen_id: 1,
  cnj_number: '40008817220268260526',
  cnj_formatted: '4000881-72.2026.8.26.0526',
  case_id: null,
  tribunal: 'TJSP',
  kind: 'Intimação',
  document_type: 'Ato ordinatório',
  orgao: '1ª Vara',
  classe: '',
  available_on: '2026-11-19',
  text: 'Intime-se o autor para, no prazo de 15 (quinze) dias, manifestar-se.',
  link: 'https://tj.example/doc',
  recipients: [],
  deadline_hints: ['15 dias'],
  oab_label: 'OAB 123456/SP · Dra. Ana',
  status: 'NEW',
  handled_at: null,
  handled_by_name: '',
  created_at: '',
};

const page = <T>(results: T[]) =>
  of({ count: results.length, next: null, previous: null, results });

describe('PublicationsPage', () => {
  let fixture: ComponentFixture<PublicationsPage>;
  let api: Record<string, ReturnType<typeof vi.fn>>;

  async function setup(overrides: Partial<typeof api> = {}) {
    api = {
      listOabs: vi.fn(() => page([oab])),
      list: vi.fn(() => page([pub])),
      mark: vi.fn(() => of({ ...pub, status: 'DONE' })),
      createCase: vi.fn(() => of({ case_id: 'c1' })),
      createOab: vi.fn(() => of(oab)),
      foundCases: vi.fn(() =>
        of([
          {
            cnj_number: '40008817220268260526',
            cnj_formatted: '4000881-72.2026.8.26.0526',
            tribunal: 'TJSP',
            classe: 'Procedimento comum cível',
            orgao: '1ª Vara',
            last_on: '2026-11-10',
            count: 3,
            oab_label: 'OAB 123456/SP',
          },
        ]),
      ),
      importCases: vi.fn(() => of({ created: 1, skipped: 0 })),
      ...overrides,
    };
    await TestBed.configureTestingModule({
      imports: [PublicationsPage],
      providers: [
        provideRouter([{ path: '**', children: [] }]),
        { provide: PublicationsService, useValue: api },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(PublicationsPage);
    await fixture.whenStable();
  }

  const el = () => fixture.nativeElement as HTMLElement;
  const button = (label: string) =>
    [...el().querySelectorAll('button')].find((b) => b.textContent?.includes(label));

  it('mostra OABs, a publicação nova e a dica de prazo sem calcular', async () => {
    await setup();
    expect(api['list']).toHaveBeenCalledWith({ status: 'NEW', q: '' }, 0, 20);
    expect(el().textContent).toContain('OAB 123456/SP');
    expect(el().textContent).toContain('1 nova(s)');
    expect(el().textContent).toContain('4000881-72.2026.8.26.0526');
    expect(el().textContent).toContain('menciona prazo de 15 dias');
    expect(el().textContent).toContain('não calcula prazos');
    const link = el().querySelector<HTMLAnchorElement>('a[target="_blank"]');
    expect(link?.rel).toContain('noopener');
  });

  it('marca como tratada e cadastra o processo', async () => {
    await setup();
    button('Marcar como tratada')?.click();
    expect(api['mark']).toHaveBeenCalledWith('p1', 'DONE');
    button('Cadastrar processo')?.click();
    expect(api['createCase']).toHaveBeenCalledWith('p1');
  });

  it('plano sem publicações mostra o aviso de upgrade', async () => {
    const locked = () =>
      throwError(
        () =>
          new HttpErrorResponse({
            status: 402,
            error: { error: { code: 'plan_feature', message: 'Planos Escritório e Equipe.' } },
          }),
      );
    await setup({ listOabs: vi.fn(locked), list: vi.fn(locked), foundCases: vi.fn(locked) });
    fixture.detectChanges();
    expect(el().textContent).toContain('Disponível nos planos Escritório e Equipe');
    expect(button('Adicionar OAB')).toBeUndefined();
  });

  it('lista processos encontrados no Diário e cadastra os marcados', async () => {
    await setup();
    expect(el().textContent).toContain('Processos encontrados no Diário (1)');
    expect(el().textContent).toContain('5 publicação(ões)');
    button('Marcar todos')?.click();
    fixture.detectChanges();
    button('Cadastrar 1 processo(s)')?.click();
    expect(api['importCases']).toHaveBeenCalledWith(['40008817220268260526']);
  });

  it('diz o que falta quando a OAB não pode ser adicionada', async () => {
    await setup();
    fixture.componentInstance.number.setValue('123456');
    fixture.componentInstance.addOab();
    fixture.detectChanges();
    expect(api['createOab']).not.toHaveBeenCalled();
    expect(el().textContent).toContain('Falta preencher a UF (estado da OAB).');
    fixture.componentInstance.uf.setValue('SP');
    fixture.componentInstance.addOab();
    expect(api['createOab']).toHaveBeenCalledWith({
      number: '123456',
      uf: 'SP',
      lawyer_name: '',
    });
  });
});
