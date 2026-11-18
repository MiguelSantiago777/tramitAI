import { daysFromHours, hoursFromDays } from './business-hours';

describe('horário de atendimento', () => {
  it('ida e volta entre a API e o formulário', () => {
    const api = {
      '0': [
        ['09:00', '12:00'],
        ['13:00', '18:00'],
      ],
      '1': [['08:00', '17:00']],
      '2': [],
      '3': [],
      '4': [],
      '5': [],
      '6': [],
    } as Record<string, [string, string][]>;
    const days = daysFromHours(api);
    expect(days[0]).toEqual({
      open: true,
      start: '09:00',
      end: '18:00',
      hasBreak: true,
      breakStart: '12:00',
      breakEnd: '13:00',
    });
    expect(days[1].hasBreak).toBe(false);
    expect(days[2].open).toBe(false);
    expect(hoursFromDays(days)).toEqual(api);
  });
});
