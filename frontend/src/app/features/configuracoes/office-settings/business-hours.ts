/** Horário de atendimento: formato da API ↔ formulário (um dia por linha, com intervalo). */

export type BusinessHours = Record<string, [string, string][]>;

export interface DayHours {
  open: boolean;
  start: string;
  end: string;
  hasBreak: boolean;
  breakStart: string;
  breakEnd: string;
}

// Índice 0 = segunda (mesma convenção do backend).
export const DAY_NAMES = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];

export function daysFromHours(hours: BusinessHours | null | undefined): DayHours[] {
  return DAY_NAMES.map((_, i) => {
    const periods = hours?.[String(i)] ?? [];
    if (periods.length === 0) {
      return {
        open: false,
        start: '09:00',
        end: '18:00',
        hasBreak: true,
        breakStart: '12:00',
        breakEnd: '13:00',
      };
    }
    const first = periods[0];
    const last = periods[periods.length - 1];
    return {
      open: true,
      start: first[0],
      end: last[1],
      hasBreak: periods.length > 1,
      breakStart: periods.length > 1 ? first[1] : '12:00',
      breakEnd: periods.length > 1 ? periods[1][0] : '13:00',
    };
  });
}

export function hoursFromDays(days: DayHours[]): BusinessHours {
  const out: BusinessHours = {};
  days.forEach((d, i) => {
    if (!d.open) {
      out[String(i)] = [];
    } else if (d.hasBreak) {
      out[String(i)] = [
        [d.start, d.breakStart],
        [d.breakEnd, d.end],
      ];
    } else {
      out[String(i)] = [[d.start, d.end]];
    }
  });
  return out;
}
