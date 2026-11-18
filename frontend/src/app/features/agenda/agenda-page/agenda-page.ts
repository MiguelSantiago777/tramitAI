import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';

import { toApiError } from '../../../core/http/api-error';
import { CalendarEvent, EVENT_KIND_LABELS, isoDate, todayIso } from '../agenda.models';
import { AgendaService } from '../agenda.service';
import { EventDialog, EventDialogData } from '../event-dialog/event-dialog';
import { GoogleCalendarCard } from '../google-calendar-card';

interface Day {
  iso: string;
  date: Date;
  isToday: boolean;
  events: CalendarEvent[];
}

function mondayOf(date: Date): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const weekday = (d.getDay() + 6) % 7; // segunda = 0
  d.setDate(d.getDate() - weekday);
  return d;
}

function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

/** Agenda da semana: audiências, reuniões e atendimentos. */
@Component({
  selector: 'app-agenda-page',
  imports: [
    DatePipe,
    RouterLink,
    MatButtonModule,
    MatProgressBarModule,
    MatTooltipModule,
    GoogleCalendarCard,
  ],
  templateUrl: './agenda-page.html',
  styleUrl: './agenda-page.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgendaPage {
  private readonly api = inject(AgendaService);
  private readonly dialog = inject(MatDialog);
  private readonly snack = inject(MatSnackBar);

  readonly weekStart = signal(mondayOf(new Date()));
  readonly events = signal<CalendarEvent[]>([]);
  /** Pré-reservas da Lia nos próximos 30 dias (independe da semana na tela). */
  readonly pending = signal<CalendarEvent[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly weekEnd = computed(() => addDays(this.weekStart(), 6));
  readonly days = computed<Day[]>(() => {
    const today = todayIso();
    const byDay = new Map<string, CalendarEvent[]>();
    for (const e of this.events()) {
      const key = isoDate(new Date(e.starts_at));
      byDay.set(key, [...(byDay.get(key) ?? []), e]);
    }
    return Array.from({ length: 7 }, (_, i) => {
      const date = addDays(this.weekStart(), i);
      const iso = isoDate(date);
      return { iso, date, isToday: iso === today, events: byDay.get(iso) ?? [] };
    });
  });
  readonly isCurrentWeek = computed(
    () => isoDate(this.weekStart()) === isoDate(mondayOf(new Date())),
  );

  constructor() {
    this.load();
  }

  kindLabel(e: CalendarEvent): string {
    return EVENT_KIND_LABELS[e.kind];
  }

  move(weeks: number): void {
    this.weekStart.update((d) => addDays(d, weeks * 7));
    this.load();
  }

  goToday(): void {
    this.weekStart.set(mondayOf(new Date()));
    this.load();
  }

  create(date?: string): void {
    this.openDialog({ defaults: { date: date ?? todayIso() } });
  }

  open(event: CalendarEvent): void {
    this.openDialog({ event });
  }

  private openDialog(data: EventDialogData): void {
    this.dialog
      .open(EventDialog, { data, width: '640px', maxWidth: '95vw', autoFocus: 'first-tabbable' })
      .afterClosed()
      .subscribe((saved?: CalendarEvent) => {
        if (saved) {
          this.load();
        }
      });
  }

  confirm(e: CalendarEvent): void {
    this.api.confirmEvent(e.id).subscribe({
      next: () => {
        this.snack.open('Confirmado. O contato recebeu a confirmação no WhatsApp.', 'OK', {
          duration: 4000,
        });
        this.load();
      },
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }

  decline(e: CalendarEvent): void {
    this.api.declineEvent(e.id).subscribe({
      next: () => this.load(),
      error: (err: unknown) => this.error.set(toApiError(err).message),
    });
  }

  private loadPending(): void {
    const today = new Date();
    this.api.events({ start: isoDate(today), end: isoDate(addDays(today, 30)) }).subscribe({
      next: (page) => this.pending.set(page.results.filter((e) => e.status === 'PENDING')),
      error: () => this.pending.set([]),
    });
  }

  private load(): void {
    this.loadPending();
    this.loading.set(true);
    this.error.set(null);
    this.api.events({ start: isoDate(this.weekStart()), end: isoDate(this.weekEnd()) }).subscribe({
      next: (page) => {
        this.loading.set(false);
        this.events.set(page.results);
      },
      error: (err: unknown) => {
        this.loading.set(false);
        this.error.set(toApiError(err).message);
      },
    });
  }
}
