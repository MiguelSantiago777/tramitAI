import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page, listParams } from '../../core/http/page';
import {
  AcceptanceChannel,
  Client,
  ClientInput,
  ClientStatus,
  TermAcceptance,
} from './client.models';

const URL = '/api/v1/clients/';

export interface ClientFilters {
  q?: string;
  status?: ClientStatus | '';
}

@Injectable({ providedIn: 'root' })
export class ClientsService {
  private readonly http = inject(HttpClient);

  list(filters: ClientFilters = {}, pageIndex = 0, pageSize = 25): Observable<Page<Client>> {
    return this.http.get<Page<Client>>(URL, {
      params: listParams({ ...filters }, pageIndex, pageSize),
    });
  }

  get(id: string): Observable<Client> {
    return this.http.get<Client>(`${URL}${id}/`);
  }

  create(input: ClientInput): Observable<Client> {
    return this.http.post<Client>(URL, input);
  }

  update(id: string, input: Partial<ClientInput>): Observable<Client> {
    return this.http.patch<Client>(`${URL}${id}/`, input);
  }

  termAcceptances(id: string): Observable<TermAcceptance[]> {
    return this.http.get<TermAcceptance[]>(`${URL}${id}/term-acceptances/`);
  }

  registerTermAcceptance(
    id: string,
    body: { channel: AcceptanceChannel; evidence: string },
  ): Observable<TermAcceptance> {
    return this.http.post<TermAcceptance>(`${URL}${id}/term-acceptances/`, body);
  }
}
