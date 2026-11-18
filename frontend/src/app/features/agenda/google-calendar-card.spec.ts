import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { GoogleCalendarCard, GoogleStatus } from './google-calendar-card';

const URL = '/api/v1/agenda/google/';

describe('GoogleCalendarCard', () => {
  async function setup(status: GoogleStatus) {
    await TestBed.configureTestingModule({
      imports: [GoogleCalendarCard],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    const fixture = TestBed.createComponent(GoogleCalendarCard);
    const http = TestBed.inject(HttpTestingController);
    http.expectOne(URL).flush(status);
    await fixture.whenStable();
    return { fixture, http, text: () => (fixture.nativeElement as HTMLElement).textContent ?? '' };
  }

  const base: GoogleStatus = {
    configured: true,
    connected: false,
    google_email: '',
    needs_reconnect: false,
    busy_synced_at: null,
  };

  it('convida a conectar', async () => {
    const { text } = await setup(base);
    expect(text()).toContain('Conecte seu Google Agenda');
    expect(text()).toContain('Conectar');
  });

  it('mostra a conta conectada e pede reconexão quando vence', async () => {
    const ok = await setup({ ...base, connected: true, google_email: 'dra@gmail.com' });
    expect(ok.text()).toContain('dra@gmail.com');
    expect(ok.text()).not.toContain('Reconectar');
    TestBed.resetTestingModule();
    const expired = await setup({ ...base, connected: true, needs_reconnect: true });
    expect(expired.text()).toContain('Reconectar');
  });

  it('some quando o servidor não tem a integração configurada', async () => {
    const { text } = await setup({ ...base, configured: false });
    expect(text().trim()).toBe('');
  });
});
