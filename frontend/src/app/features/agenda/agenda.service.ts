import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page, listParams } from '../../core/http/page';
import { CalendarEvent, Desk, EventInput, Task, TaskInput, TaskStatus } from './agenda.models';

export interface TaskFilters {
  status?: TaskStatus | '';
  assignee?: string; // 'me' | 'none' | id
  due?: '' | 'overdue' | 'today' | 'week' | 'none';
  client_id?: string;
  case_id?: string;
  q?: string;
}

export interface EventFilters {
  start?: string;
  end?: string;
  client_id?: string;
  case_id?: string;
}

@Injectable({ providedIn: 'root' })
export class AgendaService {
  private readonly http = inject(HttpClient);

  desk(): Observable<Desk> {
    return this.http.get<Desk>('/api/v1/my-desk/');
  }

  tasks(filters: TaskFilters = {}, pageIndex = 0, pageSize = 50): Observable<Page<Task>> {
    return this.http.get<Page<Task>>('/api/v1/tasks/', {
      params: listParams({ ...filters }, pageIndex, pageSize),
    });
  }

  createTask(input: TaskInput): Observable<Task> {
    return this.http.post<Task>('/api/v1/tasks/', input);
  }

  updateTask(id: string, input: Partial<TaskInput>): Observable<Task> {
    return this.http.patch<Task>(`/api/v1/tasks/${id}/`, input);
  }

  completeTask(id: string): Observable<Task> {
    return this.http.post<Task>(`/api/v1/tasks/${id}/complete/`, {});
  }

  reopenTask(id: string): Observable<Task> {
    return this.http.post<Task>(`/api/v1/tasks/${id}/reopen/`, {});
  }

  events(filters: EventFilters = {}): Observable<Page<CalendarEvent>> {
    return this.http.get<Page<CalendarEvent>>('/api/v1/events/', {
      params: listParams({ ...filters }, 0, 100),
    });
  }

  createEvent(input: EventInput): Observable<CalendarEvent> {
    return this.http.post<CalendarEvent>('/api/v1/events/', input);
  }

  /** Confirma o horário pré-reservado pela Lia (o contato recebe a confirmação). */
  confirmEvent(id: string): Observable<CalendarEvent> {
    return this.http.post<CalendarEvent>(`/api/v1/events/${id}/confirm/`, {});
  }

  declineEvent(id: string): Observable<CalendarEvent> {
    return this.http.post<CalendarEvent>(`/api/v1/events/${id}/decline/`, {});
  }

  updateEvent(id: string, input: Partial<EventInput>): Observable<CalendarEvent> {
    return this.http.patch<CalendarEvent>(`/api/v1/events/${id}/`, input);
  }
}
