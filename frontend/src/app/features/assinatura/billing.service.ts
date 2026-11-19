import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';

export type BillingStatusCode =
  'TRIAL' | 'PENDING' | 'ACTIVE' | 'PAST_DUE' | 'CANCELLED' | 'EXEMPT';

export interface Billing {
  status: BillingStatusCode;
  status_label: string;
  plan_name: string;
  price: string;
  trial_ends_at: string | null;
  paid_until: string | null;
  access_until: string | null;
  days_left: number | null;
  blocked: boolean;
  payer_email: string;
  checkout_url: string;
  can_manage: boolean;
  exempt: boolean;
  plan_code: string;
  users_used: number;
  users_limit: number | null;
  ai_used: number;
  ai_limit: number | null;
}

export interface Plan {
  code: string;
  name: string;
  price: string;
  description: string;
  max_users: number | null;
  monthly_ai_limit: number | null;
}

const URL = '/api/v1/billing/';

@Injectable({ providedIn: 'root' })
export class BillingService {
  private readonly http = inject(HttpClient);
  /** Último estado conhecido (o menu mostra o aviso de teste/vencimento). */
  readonly current = signal<Billing | null>(null);

  load(): Observable<Billing> {
    return this.http.get<Billing>(URL).pipe(tap((b) => this.current.set(b)));
  }

  refresh(): Observable<Billing> {
    return this.http.post<Billing>(`${URL}refresh/`, {}).pipe(tap((b) => this.current.set(b)));
  }

  checkout(payerEmail: string): Observable<{ checkout_url: string }> {
    return this.http.post<{ checkout_url: string }>(URL, { payer_email: payerEmail });
  }

  cancel(): Observable<Billing> {
    return this.http.delete<Billing>(URL).pipe(tap((b) => this.current.set(b)));
  }

  changePlan(planCode: string): Observable<Billing> {
    return this.http
      .post<Billing>(`${URL}plan/`, { plan_code: planCode })
      .pipe(tap((b) => this.current.set(b)));
  }

  plans(): Observable<Plan[]> {
    return this.http.get<Plan[]>(`${URL}plans/`);
  }
}

/** Aviso no topo: teste acabando, pagamento pendente/atrasado, bloqueado ou Vera no limite. */
export function billingNotice(b: Billing | null): string | null {
  if (!b || b.exempt) return null;
  if (b.blocked) return 'Acesso bloqueado: a assinatura venceu.';
  if (b.ai_limit !== null && b.ai_used >= b.ai_limit) {
    return 'A Vera atingiu o limite do plano neste mês: responda as conversas manualmente ou mude de plano.';
  }
  if (b.status === 'TRIAL' && b.days_left !== null && b.days_left <= 7) {
    return b.days_left === 0
      ? 'Seu teste grátis termina hoje.'
      : `Seu teste grátis termina em ${b.days_left} dia(s).`;
  }
  if (b.status === 'PAST_DUE') return 'Pagamento da assinatura atrasado.';
  if (b.status === 'PENDING') return 'Assinatura aguardando pagamento.';
  if (b.status === 'CANCELLED')
    return 'Assinatura cancelada: o acesso vai até o fim do período pago.';
  if (b.ai_limit !== null && b.ai_used >= b.ai_limit * 0.8) {
    return `A Vera já usou ${b.ai_used} de ${b.ai_limit} mensagens do plano neste mês.`;
  }
  return null;
}
