import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { Draft } from '../draft.models';
import { DraftsService } from '../drafts.service';
import { DraftCard } from './draft-card';

const base: Draft = {
  id: 'd1',
  conversation_id: 'c1',
  contact_name: 'Maria (perfil)',
  phone: '+5521998765432',
  client_id: 'cl1',
  client_name: 'Maria da Silva',
  origin: 'AI_REPLY',
  status: 'DRAFT',
  generated_body: 'Olá! Vou verificar com o advogado.',
  final_body: '',
  original_ai_text: '',
  intent: 'case_status',
  urgency: 'high',
  needs_lawyer: true,
  summary: 'Cliente pergunta da audiência.',
  guardrail_flags: [],
  source_text: 'Minha audiência é quando?',
  window_open: true,
  decided_by_name: '',
  decided_at: null,
  rejection_reason: '',
  failure_detail: '',
  sent_message_status: '',
  created_at: '2026-11-17T10:00:00Z',
};

describe('DraftCard', () => {
  let fixture: ComponentFixture<DraftCard>;
  let api: { approve: ReturnType<typeof vi.fn>; reject: ReturnType<typeof vi.fn> };

  async function setup(draft: Partial<Draft> = {}, canDecide = true) {
    api = {
      approve: vi.fn(() => of({ ...base, status: 'APPROVED' })),
      reject: vi.fn(() => of({ ...base, status: 'REJECTED' })),
    };
    await TestBed.configureTestingModule({
      imports: [DraftCard],
      providers: [provideRouter([]), { provide: DraftsService, useValue: api }],
    }).compileComponents();
    fixture = TestBed.createComponent(DraftCard);
    fixture.componentRef.setInput('draft', { ...base, ...draft });
    fixture.componentRef.setInput('canDecide', canDecide);
    await fixture.whenStable();
  }

  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';
  const buttons = () =>
    [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')] as HTMLButtonElement[];
  const button = (label: string) => buttons().find((b) => b.textContent?.includes(label));

  it('mostra contexto para o advogado: mensagem do cliente, resumo e urgência', async () => {
    await setup();
    expect(text()).toContain('Minha audiência é quando?');
    expect(text()).toContain('Cliente pergunta da audiência.');
    expect(text()).toContain('Urgente');
    expect(text()).toContain('Precisa de análise do advogado');
  });

  it('aprova sem edição enviando só o id', async () => {
    await setup();
    const decided = vi.fn();
    fixture.componentInstance.decided.subscribe(decided);
    button('Aprovar e enviar')!.click();
    expect(api.approve).toHaveBeenCalledWith('d1', undefined);
    expect(decided).toHaveBeenCalled();
  });

  it('aprova com o texto editado', async () => {
    await setup();
    fixture.componentInstance.body.setValue('Olá, Maria! Retorno ainda hoje.');
    fixture.componentInstance.approve();
    expect(api.approve).toHaveBeenCalledWith('d1', 'Olá, Maria! Retorno ainda hoje.');
  });

  it('rejeita com motivo', async () => {
    await setup();
    button('Rejeitar')!.click();
    await fixture.whenStable();
    fixture.componentInstance.reason.setValue('Vou ligar para ela.');
    button('Confirmar rejeição')!.click();
    expect(api.reject).toHaveBeenCalledWith('d1', 'Vou ligar para ela.');
  });

  it('não deixa aprovar com a janela de 24h fechada', async () => {
    await setup({ window_open: false });
    expect(text()).toContain('A janela de 24h está fechada');
    expect(button('Aprovar e enviar')!.disabled).toBe(true);
  });

  it('avisa quando os guardrails bloquearam o texto da IA', async () => {
    await setup({
      guardrail_flags: ['unknown_case_number'],
      original_ai_text: 'Seu processo 0009999-11.2023.8.19.0001 está ok.',
    });
    expect(text()).toContain('citou número de processo que não está no cadastro');
    expect(text()).toContain('Ver o que a IA tinha escrito');
  });

  it('sem permissão, não mostra os botões de decisão', async () => {
    await setup({}, false);
    expect(button('Aprovar e enviar')).toBeUndefined();
    expect(text()).toContain('Só advogados podem aprovar');
  });

  it('rascunho decidido mostra o texto final e quem decidiu', async () => {
    await setup({
      status: 'SENT',
      final_body: 'Texto enviado.',
      decided_by_name: 'Dra. Ana',
      decided_at: '2026-11-17T10:05:00Z',
    });
    expect(text()).toContain('Texto enviado.');
    expect(text()).toContain('Enviada');
    expect(text()).toContain('Dra. Ana');
    expect(fixture.nativeElement.querySelector('textarea')).toBeNull();
  });
});
