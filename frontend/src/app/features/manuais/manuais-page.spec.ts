import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { Manual, ManuaisPage, duration } from './manuais-page';

const LIST: Manual[] = [
  { id: 'primeiros-passos', title: 'Primeiros passos', description: 'Entrar.', seconds: 46 },
  { id: 'agenda', title: 'Agenda', description: 'Compromissos.', seconds: 60 },
];

describe('ManuaisPage', () => {
  it('toca o primeiro manual e passa para o próximo', async () => {
    await TestBed.configureTestingModule({
      imports: [ManuaisPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    const fixture = TestBed.createComponent(ManuaisPage);
    TestBed.inject(HttpTestingController).expectOne('/videos/manuais/manuais.json').flush(LIST);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('video')?.getAttribute('src')).toBe(
      '/videos/manuais/primeiros-passos.mp4',
    );
    expect(el.textContent).toContain('Próximo: Agenda');

    (el.querySelector('.player__next') as HTMLButtonElement).click();
    await fixture.whenStable();
    expect(el.querySelector('video')?.getAttribute('src')).toBe('/videos/manuais/agenda.mp4');
    expect(el.textContent).not.toContain('Próximo:');
  });

  it('formata a duração', () => {
    expect(duration(46)).toBe('46s');
    expect(duration(60)).toBe('1min');
    expect(duration(66)).toBe('1min 06s');
  });
});
