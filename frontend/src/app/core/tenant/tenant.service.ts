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

export interface TeamMember {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  pending: boolean;
  is_me: boolean;
}

export interface OfficeSettings {
  id: string;
  tenant_name: string;
  auto_send_simple_replies: boolean;
  business_hours: Record<string, [string, string][]>;
  scheduling_enabled: boolean;
  consult_minutes: number;
  scheduling_user_id: string | null;
  staff_can_approve: boolean;
  ai_triage_enabled: boolean;
  updated_at: string;
}

export interface RecentMovement {
  id: string;
  case_id: string;
  case_number: string;
  name: string;
  occurred_at: string;
  notification: 'BASELINE' | 'PENDING' | 'NOTIFIED' | 'SKIPPED';
}

export interface Dashboard {
  pending_drafts: number;
  urgent_drafts: number;
  awaiting_drafts: number;
  sent_last_7_days: number;
  unread_conversations: number;
  open_conversations: number;
  active_cases: number;
  cases_with_news: number;
  active_clients: number;
  leads: number;
  recent_movements: RecentMovement[];
}

@Injectable({ providedIn: 'root' })
export class TenantService {
  private readonly http = inject(HttpClient);

  dashboard(): Observable<Dashboard> {
    return this.http.get<Dashboard>('/api/v1/tenant/dashboard/');
  }

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

  team(): Observable<TeamMember[]> {
    return this.http.get<TeamMember[]>('/api/v1/tenant/team/');
  }

  invite(body: { email: string; full_name: string; role: Role }): Observable<TeamMember> {
    return this.http.post<TeamMember>('/api/v1/tenant/team/', body);
  }

  updateMember(id: string, body: { role?: Role; is_active?: boolean }): Observable<TeamMember> {
    return this.http.patch<TeamMember>(`/api/v1/tenant/team/${id}/`, body);
  }

  resendInvite(id: string): Observable<void> {
    return this.http.post<void>(`/api/v1/tenant/team/${id}/resend-invite/`, {});
  }

  settings(): Observable<OfficeSettings> {
    return this.http.get<OfficeSettings>('/api/v1/tenant/settings/');
  }

  updateSettings(body: Partial<OfficeSettings>): Observable<OfficeSettings> {
    return this.http.patch<OfficeSettings>('/api/v1/tenant/settings/', body);
  }
}
