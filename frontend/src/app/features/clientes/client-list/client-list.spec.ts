import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { ClientsService } from '../clients.service';
import { ClientList } from './client-list';

describe('ClientList', () => {
  it('lista clientes com documento e telefone formatados e filtra por situação', async () => {
    const list = vi.fn(() =>
      of({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: 'c1',
            kind: 'PF',
            name: 'Maria da Silva',
            cpf_cnpj: '52998224725',
            phone: '+5521998765432',
            email: '',
            status: 'LEAD',
            notes: '',
            tags: [],
            created_at: '',
            updated_at: '',
          },
        ],
      }),
    );
    await TestBed.configureTestingModule({
      imports: [ClientList],
      providers: [
        provideRouter([]),
        { provide: ClientsService, useValue: { list, tags: vi.fn(() => of([])) } },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(ClientList);
    await fixture.whenStable();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';

    expect(text).toContain('Maria da Silva');
    expect(text).toContain('529.982.247-25');
    expect(text).toContain('(21) 99876-5432');
    expect(text).toContain('Lead');

    fixture.componentInstance.status.setValue('ARCHIVED');
    expect(list).toHaveBeenLastCalledWith({ q: '', status: 'ARCHIVED', tag_id: '' }, 0, 25);
  });
});
