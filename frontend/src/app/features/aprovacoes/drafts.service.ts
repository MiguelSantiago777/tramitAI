import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page, listParams } from '../../core/http/page';
import { Draft, DraftStatus } from './draft.models';

const URL = '/api/v1/drafts/';

@Injectable({ providedIn: 'root' })
export class DraftsService {
  private readonly http = inject(HttpClient);

  list(
    filters: { status?: DraftStatus | ''; conversation_id?: string } = {},
    pageIndex = 0,
    pageSize = 25,
  ): Observable<Page<Draft>> {
    return this.http.get<Page<Draft>>(URL, {
      params: listParams({ ...filters }, pageIndex, pageSize),
    });
  }

  get(id: string): Observable<Draft> {
    return this.http.get<Draft>(`${URL}${id}/`);
  }

  /** `body` ausente = envia o texto gerado sem edição. */
  approve(id: string, body?: string): Observable<Draft> {
    return this.http.post<Draft>(`${URL}${id}/approve/`, body === undefined ? {} : { body });
  }

  reject(id: string, reason: string): Observable<Draft> {
    return this.http.post<Draft>(`${URL}${id}/reject/`, { reason });
  }
}
