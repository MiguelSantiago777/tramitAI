import { HttpEventType } from '@angular/common/http';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { AuthService } from '../../core/auth/auth.service';
import { DocumentsPanel } from './documents-panel';
import { DocumentItem } from './documents.models';
import { DocumentsService } from './documents.service';
import { MessageMedia } from './message-media';

const rg: DocumentItem = {
  id: 'd1',
  name: 'rg.pdf',
  content_type: 'application/pdf',
  size: 2048,
  category: 'PESSOAL',
  category_label: 'Documento pessoal',
  description: '',
  source: 'UPLOAD',
  client_id: 'c1',
  client_name: 'Ana',
  legal_case_id: null,
  case_number: '',
  conversation_id: null,
  message_id: null,
  uploaded_by_name: 'Dra. Bia',
  can_preview: true,
  created_at: '2026-11-18T10:00:00Z',
};
const holerite: DocumentItem = {
  ...rg,
  id: 'd2',
  name: 'holerite.jpg',
  content_type: 'image/jpeg',
  category: 'WHATSAPP',
  category_label: 'Recebido no WhatsApp',
  source: 'WHATSAPP',
  conversation_id: 'conv1',
  uploaded_by_name: '',
};

describe('DocumentsPanel', () => {
  let fixture: ComponentFixture<DocumentsPanel>;
  let api: Record<string, ReturnType<typeof vi.fn>>;

  async function setup(role: 'OWNER' | 'STAFF') {
    api = {
      list: vi.fn(() => of({ count: 2, next: null, previous: null, results: [rg, holerite] })),
      upload: vi.fn(() =>
        of({ type: HttpEventType.Response, body: { ...rg, id: 'd3', name: 'novo.pdf' } }),
      ),
      update: vi.fn(),
      remove: vi.fn(() => of(undefined)),
      open: vi.fn(),
      download: vi.fn(),
    };
    await TestBed.configureTestingModule({
      imports: [DocumentsPanel],
      providers: [
        provideRouter([]),
        { provide: DocumentsService, useValue: api },
        { provide: AuthService, useValue: { session: signal({ role }) } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(DocumentsPanel);
    fixture.componentRef.setInput('clientId', 'c1');
    await fixture.whenStable();
  }

  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';

  it('lista os documentos do cliente, inclusive os que vieram do WhatsApp', async () => {
    await setup('OWNER');
    expect(api['list']).toHaveBeenCalledWith({ client: 'c1' });
    expect(text()).toContain('rg.pdf');
    expect(text()).toContain('2 KB');
    expect(text()).toContain('por Dra. Bia');
    expect(text()).toContain('pelo WhatsApp');
  });

  it('envia o arquivo escolhido para o cliente com o tipo selecionado', async () => {
    await setup('OWNER');
    const panel = fixture.componentInstance;
    panel.category.setValue('CONTRATO');
    const file = new File(['%PDF'], 'novo.pdf', { type: 'application/pdf' });
    panel.onDrop({
      preventDefault: () => undefined,
      dataTransfer: { files: [file] },
    } as unknown as DragEvent);
    await fixture.whenStable();
    expect(api['upload']).toHaveBeenCalledWith(
      expect.objectContaining({ file, client_id: 'c1', category: 'CONTRATO' }),
    );
    expect(panel.docs()[0].name).toBe('novo.pdf');
  });

  it('recusa arquivo grande antes de enviar', async () => {
    await setup('OWNER');
    const big = new File(['x'], 'video.mp4');
    Object.defineProperty(big, 'size', { value: 30 * 1024 * 1024 });
    fixture.componentInstance.onDrop({
      preventDefault: () => undefined,
      dataTransfer: { files: [big] },
    } as unknown as DragEvent);
    expect(api['upload']).not.toHaveBeenCalled();
    expect(fixture.componentInstance.error()).toContain('25 MB');
  });

  it('só titular ou advogado pode apagar', async () => {
    await setup('STAFF');
    expect(fixture.componentInstance.canDelete()).toBe(false);
  });
});

describe('MessageMedia', () => {
  it('mostra "guardando" enquanto a mídia não chegou e o arquivo depois', async () => {
    const api = { objectUrl: vi.fn(() => of('blob:x')), open: vi.fn() };
    await TestBed.configureTestingModule({
      imports: [MessageMedia],
      providers: [{ provide: DocumentsService, useValue: api }],
    }).compileComponents();
    const fixture = TestBed.createComponent(MessageMedia);
    fixture.componentRef.setInput('pending', true);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Guardando o arquivo');

    fixture.componentRef.setInput('pending', false);
    fixture.componentRef.setInput('doc', {
      id: 'd1',
      name: 'contracheque.pdf',
      content_type: 'application/pdf',
      size: 1024,
    });
    await fixture.whenStable();
    expect(el.textContent).toContain('contracheque.pdf');
    (el.querySelector('button') as HTMLButtonElement).click();
    expect(api.open).toHaveBeenCalledWith({
      id: 'd1',
      name: 'contracheque.pdf',
      can_preview: true,
    });
    expect(api.objectUrl).not.toHaveBeenCalled(); // PDF não tem prévia na conversa
  });
});
