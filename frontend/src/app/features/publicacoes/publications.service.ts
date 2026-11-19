import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page, listParams } from '../../core/http/page';
import {
  MonitoredOab,
  MonitoredOabInput,
  Publication,
  PublicationStatus,
} from './publication.models';

const OABS = '/api/v1/monitored-oabs/';
const PUBS = '/api/v1/publications/';

export interface PublicationFilters {
  status?: PublicationStatus | '';
  case_id?: string;
  q?: string;
}

/** Publicações do Diário (DJEN) e as OABs monitoradas. */
@Injectable({ providedIn: 'root' })
export class PublicationsService {
  private readonly http = inject(HttpClient);

  listOabs(): Observable<Page<MonitoredOab>> {
    return this.http.get<Page<MonitoredOab>>(OABS, { params: listParams({}, 0, 100) });
  }

  createOab(input: MonitoredOabInput): Observable<MonitoredOab> {
    return this.http.post<MonitoredOab>(OABS, input);
  }

  updateOab(id: string, input: Partial<MonitoredOabInput>): Observable<MonitoredOab> {
    return this.http.patch<MonitoredOab>(`${OABS}${id}/`, input);
  }

  deleteOab(id: string): Observable<void> {
    return this.http.delete<void>(`${OABS}${id}/`);
  }

  /** Busca agora no DJEN (assíncrona: 202). */
  checkOab(id: string): Observable<void> {
    return this.http.post<void>(`${OABS}${id}/check/`, {});
  }

  list(
    filters: PublicationFilters = {},
    pageIndex = 0,
    pageSize = 20,
  ): Observable<Page<Publication>> {
    return this.http.get<Page<Publication>>(PUBS, {
      params: listParams({ ...filters }, pageIndex, pageSize),
    });
  }

  mark(id: string, status: PublicationStatus): Observable<Publication> {
    return this.http.post<Publication>(`${PUBS}${id}/mark/`, { status });
  }

  createCase(id: string): Observable<{ case_id: string }> {
    return this.http.post<{ case_id: string }>(`${PUBS}${id}/create-case/`, {});
  }

  summary(): Observable<{ new: number }> {
    return this.http.get<{ new: number }>(`${PUBS}summary/`);
  }
}
