import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page, listParams } from '../../core/http/page';
import { CaseStatus, LegalCase, LegalCaseInput } from './case.models';

const URL = '/api/v1/cases/';

export interface CaseFilters {
  q?: string;
  status?: CaseStatus | '';
  client_id?: string;
}

@Injectable({ providedIn: 'root' })
export class CasesService {
  private readonly http = inject(HttpClient);

  list(filters: CaseFilters = {}, pageIndex = 0, pageSize = 25): Observable<Page<LegalCase>> {
    return this.http.get<Page<LegalCase>>(URL, {
      params: listParams({ ...filters }, pageIndex, pageSize),
    });
  }

  get(id: string): Observable<LegalCase> {
    return this.http.get<LegalCase>(`${URL}${id}/`);
  }

  create(input: LegalCaseInput): Observable<LegalCase> {
    return this.http.post<LegalCase>(URL, input);
  }

  update(id: string, input: Partial<LegalCaseInput>): Observable<LegalCase> {
    return this.http.patch<LegalCase>(`${URL}${id}/`, input);
  }
}
