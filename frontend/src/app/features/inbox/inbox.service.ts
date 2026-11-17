import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page, listParams } from '../../core/http/page';
import { Conversation, ConversationStatus, Message } from './inbox.models';

const URL = '/api/v1/conversations/';

export interface ConversationFilters {
  q?: string;
  status?: ConversationStatus | '';
  unread?: boolean;
}

@Injectable({ providedIn: 'root' })
export class InboxService {
  private readonly http = inject(HttpClient);

  list(filters: ConversationFilters = {}, pageSize = 50): Observable<Page<Conversation>> {
    return this.http.get<Page<Conversation>>(URL, {
      params: listParams(
        { q: filters.q, status: filters.status, unread: filters.unread ? 'true' : '' },
        0,
        pageSize,
      ),
    });
  }

  get(id: string): Observable<Conversation> {
    return this.http.get<Conversation>(`${URL}${id}/`);
  }

  /** Mensagens da mais recente para a mais antiga. `page` começa em 1. */
  messages(id: string, page = 1, pageSize = 50): Observable<Page<Message>> {
    const params = new HttpParams().set('page', page).set('page_size', pageSize);
    return this.http.get<Page<Message>>(`${URL}${id}/messages/`, { params });
  }

  send(id: string, body: string): Observable<Message> {
    return this.http.post<Message>(`${URL}${id}/messages/`, { body });
  }

  markRead(id: string): Observable<void> {
    return this.http.post<void>(`${URL}${id}/read/`, {});
  }

  update(
    id: string,
    changes: { client_id?: string | null; status?: ConversationStatus },
  ): Observable<Conversation> {
    return this.http.patch<Conversation>(`${URL}${id}/`, changes);
  }
}
