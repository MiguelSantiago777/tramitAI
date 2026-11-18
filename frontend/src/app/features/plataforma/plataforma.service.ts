import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type OfficeStatus =
  'TRIAL' | 'PENDING' | 'ACTIVE' | 'PAST_DUE' | 'CANCELLED' | 'EXEMPT' | 'SUSPENDED';

export interface Usage {
  members: number;
  clients: number;
  messages_in: number;
  messages_out: number;
  ai_calls: number;
}

export interface Office {
  id: string;
  name: string;
  created_at: string;
  status: OfficeStatus;
  plan_code: string;
  plan_name: string;
  price: string | null;
  trial_ends_at: string | null;
  paid_until: string | null;
  access_until: string | null;
  blocked: boolean;
  owner_name: string;
  owner_email: string;
  last_payment_at: string | null;
  checkout_url: string;
  usage?: Usage;
}

export interface PlatformPayment {
  id: number;
  office_id: string;
  office_name: string;
  source: 'MERCADOPAGO' | 'MANUAL';
  status: 'PAID' | 'FAILED' | 'PENDING';
  amount: string;
  paid_at: string;
  note: string;
  created_by: string;
}

export interface OfficeDetail extends Office {
  payments: PlatformPayment[];
  history: { at: string; action: string; by: string; data: Record<string, string> }[];
}

export interface Overview {
  mrr: string;
  offices: number;
  by_status: Partial<Record<OfficeStatus, number>>;
  conversion: number | null;
  trials_ending: Office[];
  attention: Office[];
  revenue_by_month: { month: string; total: string }[];
  signups_by_week: { week: string; count: number }[];
}

export interface PlatformPlan {
  id: number;
  code: string;
  name: string;
  price: string;
  description: string;
  max_users: number | null;
  is_active: boolean;
  sort: number;
}

export const STATUS_LABELS: Record<OfficeStatus, string> = {
  TRIAL: 'Teste grátis',
  PENDING: 'Aguardando pagamento',
  ACTIVE: 'Ativa',
  PAST_DUE: 'Pagamento atrasado',
  CANCELLED: 'Cancelada',
  EXEMPT: 'Isenta',
  SUSPENDED: 'Bloqueado',
};

/** Cor do .badge global para cada situação. */
export const STATUS_BADGE: Record<OfficeStatus, string> = {
  TRIAL: 'OPEN',
  PENDING: 'PENDING',
  ACTIVE: 'PAID',
  PAST_DUE: 'OVERDUE',
  CANCELLED: 'ARCHIVED',
  EXEMPT: 'AWAITING',
  SUSPENDED: 'OVERDUE',
};

export const ACTION_LABELS: Record<string, string> = {
  'platform.trial_extended': 'Teste estendido',
  'platform.exempt_on': 'Marcado como isento',
  'platform.exempt_off': 'Isenção removida',
  'platform.suspended': 'Escritório bloqueado',
  'platform.unsuspended': 'Escritório desbloqueado',
  'platform.plan_changed': 'Plano trocado',
  'platform.manual_payment': 'Pagamento lançado',
};

const API = '/api/v1/platform/';

@Injectable({ providedIn: 'root' })
export class PlataformaService {
  private readonly http = inject(HttpClient);

  overview(): Observable<Overview> {
    return this.http.get<Overview>(`${API}overview/`);
  }

  offices(q = '', status = ''): Observable<Office[]> {
    return this.http.get<Office[]>(`${API}offices/`, { params: { q, status } });
  }

  office(id: string): Observable<OfficeDetail> {
    return this.http.get<OfficeDetail>(`${API}offices/${id}/`);
  }

  action(id: string, action: string, body: Record<string, unknown>): Observable<OfficeDetail> {
    return this.http.post<OfficeDetail>(`${API}offices/${id}/${action}/`, body);
  }

  paymentLink(id: string): Observable<{ checkout_url: string }> {
    return this.http.post<{ checkout_url: string }>(`${API}offices/${id}/payment-link/`, {});
  }

  payments(): Observable<PlatformPayment[]> {
    return this.http.get<PlatformPayment[]>(`${API}payments/`);
  }

  plans(): Observable<PlatformPlan[]> {
    return this.http.get<PlatformPlan[]>(`${API}plans/`);
  }

  savePlan(plan: Partial<PlatformPlan>): Observable<PlatformPlan> {
    return plan.id
      ? this.http.patch<PlatformPlan>(`${API}plans/${plan.id}/`, plan)
      : this.http.post<PlatformPlan>(`${API}plans/`, plan);
  }
}
