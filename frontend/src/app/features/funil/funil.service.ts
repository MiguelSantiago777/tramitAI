import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { BoardSummary, Opportunity, OpportunityInput, Stage } from './funil.models';

const URL = '/api/v1/opportunities/';

@Injectable({ providedIn: 'root' })
export class FunilService {
  private readonly http = inject(HttpClient);

  board(
    filters: { owner?: string; q?: string; client_id?: string } = {},
  ): Observable<Opportunity[]> {
    const params: Record<string, string> = {};
    for (const [k, v] of Object.entries(filters)) {
      if (v) {
        params[k] = v;
      }
    }
    return this.http.get<Opportunity[]>(URL, { params });
  }

  summary(): Observable<BoardSummary> {
    return this.http.get<BoardSummary>(`${URL}summary/`);
  }

  create(input: OpportunityInput): Observable<Opportunity> {
    return this.http.post<Opportunity>(URL, input);
  }

  update(id: string, input: OpportunityInput): Observable<Opportunity> {
    return this.http.patch<Opportunity>(`${URL}${id}/`, input);
  }

  move(id: string, stage: Stage, position: number, lostReason = ''): Observable<Opportunity> {
    return this.http.post<Opportunity>(`${URL}${id}/move/`, {
      stage,
      position,
      lost_reason: lostReason,
    });
  }
}
