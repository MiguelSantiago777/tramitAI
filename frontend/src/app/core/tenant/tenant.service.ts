import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Role } from '../auth/auth.models';

export interface Member {
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
}

export interface TermVersion {
  id: string;
  version: number;
  body: string;
  is_active: boolean;
  created_at: string;
  created_by_name: string;
}

@Injectable({ providedIn: 'root' })
export class TenantService {
  private readonly http = inject(HttpClient);
  members(): Observable<Member[]> {
    // Sem cache: o usuário pode trocar de escritório sem recarregar a página.
    return this.http.get<Member[]>('/api/v1/tenant/members/');
  }

  activeTerm(): Observable<TermVersion> {
    return this.http.get<TermVersion>('/api/v1/tenant/term/');
  }

  termVersions(): Observable<TermVersion[]> {
    return this.http.get<TermVersion[]>('/api/v1/tenant/term/versions/');
  }

  publishTerm(body: string): Observable<TermVersion> {
    return this.http.post<TermVersion>('/api/v1/tenant/term/', { body });
  }
}
