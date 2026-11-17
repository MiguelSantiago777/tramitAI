import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import {
  WhatsAppConnection,
  WhatsAppConnectionPage,
  WhatsAppConnectionService,
} from './whatsapp-connection';

const base: WhatsAppConnection = {
  provider: null,
  status: 'not_configured',
  phone: '',
  qr: null,
  can_manage: true,
};

describe('WhatsAppConnectionPage', () => {
  let fixture: ComponentFixture<WhatsAppConnectionPage>;
  let api: {
    get: ReturnType<typeof vi.fn>;
    connect: ReturnType<typeof vi.fn>;
    disconnect: ReturnType<typeof vi.fn>;
  };

  async function setup(state: Partial<WhatsAppConnection>, after?: Partial<WhatsAppConnection>) {
    api = {
      get: vi.fn(() => of({ ...base, ...state })),
      connect: vi.fn(() => of({ ...base, ...(after ?? {}) })),
      disconnect: vi.fn(() => of({ ...base, provider: 'BAILEYS', status: 'disconnected' })),
    };
    await TestBed.configureTestingModule({
      imports: [WhatsAppConnectionPage],
      providers: [{ provide: WhatsAppConnectionService, useValue: api }],
    }).compileComponents();
    fixture = TestBed.createComponent(WhatsAppConnectionPage);
    await fixture.whenStable();
  }

  afterEach(() => {
    fixture?.destroy();
    vi.useRealTimers();
  });

  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';
  const button = (label: string) =>
    [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')].find((b) =>
      b.textContent?.includes(label),
    );

  it('sem número, o titular conecta e vê o QR Code', async () => {
    await setup({}, { provider: 'BAILEYS', status: 'qr', qr: 'data:image/png;base64,AAA' });
    expect(text()).toContain('Nenhum WhatsApp conectado');
    vi.useFakeTimers();
    button('Conectar')!.click();
    fixture.detectChanges();
    expect(api.connect).toHaveBeenCalled();
    const img = (fixture.nativeElement as HTMLElement).querySelector('img');
    expect(img?.getAttribute('src')).toBe('data:image/png;base64,AAA');
    expect(text()).toContain('Aparelhos conectados');
  });

  it('enquanto espera o QR ser lido, confere o status sozinho', async () => {
    await setup({ provider: 'BAILEYS', status: 'qr', qr: 'data:x' });
    vi.useFakeTimers();
    fixture.componentInstance.refresh();
    expect(api.get).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(3000);
    expect(api.get).toHaveBeenCalledTimes(3);
  });

  it('conectado mostra o número e pede confirmação para desconectar', async () => {
    await setup({ provider: 'BAILEYS', status: 'connected', phone: '+5521912345678' });
    expect(text()).toContain('Conectado');
    expect(text()).toContain('(21) 91234-5678');
    button('Desconectar')!.click();
    fixture.detectChanges();
    expect(text()).toContain('Desconectar o WhatsApp do sistema?');
    expect(api.disconnect).not.toHaveBeenCalled();
    [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')]
      .filter((b) => b.textContent?.includes('Desconectar'))
      .at(-1)!
      .click();
    expect(api.disconnect).toHaveBeenCalled();
  });

  it('quem não é titular não conecta', async () => {
    await setup({ can_manage: false });
    expect(button('Conectar')).toBeUndefined();
    expect(text()).toContain('Só o titular pode conectar');
  });
});
