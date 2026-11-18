import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page, listParams } from '../../core/http/page';
import {
  AgreementInput,
  FeeAgreement,
  FinanceSummary,
  Installment,
  InstallmentFilter,
  MercadoPagoStatus,
  PaymentMethod,
} from './financeiro.models';

const AGREEMENTS = '/api/v1/fee-agreements/';
const INSTALLMENTS = '/api/v1/installments/';
const MP = '/api/v1/finance/mercadopago/';

export interface InstallmentFilters {
  status?: InstallmentFilter;
  client?: string;
  q?: string;
  due_from?: string;
  due_to?: string;
}

@Injectable({ providedIn: 'root' })
export class FinanceiroService {
  private readonly http = inject(HttpClient);

  agreements(client?: string): Observable<Page<FeeAgreement>> {
    return this.http.get<Page<FeeAgreement>>(AGREEMENTS, {
      params: listParams({ client: client ?? '' }, 0, 100),
    });
  }

  createAgreement(input: AgreementInput): Observable<FeeAgreement> {
    return this.http.post<FeeAgreement>(AGREEMENTS, input);
  }

  cancelAgreement(id: string): Observable<FeeAgreement> {
    return this.http.post<FeeAgreement>(`${AGREEMENTS}${id}/cancel/`, {});
  }

  installments(
    filters: InstallmentFilters,
    pageIndex = 0,
    pageSize = 25,
  ): Observable<Page<Installment>> {
    return this.http.get<Page<Installment>>(INSTALLMENTS, {
      params: listParams({ ...filters }, pageIndex, pageSize),
    });
  }

  summary(month: string): Observable<FinanceSummary> {
    return this.http.get<FinanceSummary>(`${INSTALLMENTS}summary/`, { params: { month } });
  }

  updateInstallment(
    id: string,
    body: { due_date?: string; amount?: string },
  ): Observable<Installment> {
    return this.http.patch<Installment>(`${INSTALLMENTS}${id}/`, body);
  }

  settle(
    id: string,
    body: { method: PaymentMethod; paid_amount?: string | null; paid_at?: string; note?: string },
  ): Observable<Installment> {
    return this.http.post<Installment>(`${INSTALLMENTS}${id}/settle/`, body);
  }

  reopen(id: string): Observable<Installment> {
    return this.http.post<Installment>(`${INSTALLMENTS}${id}/reopen/`, {});
  }

  cancel(id: string): Observable<Installment> {
    return this.http.post<Installment>(`${INSTALLMENTS}${id}/cancel/`, {});
  }

  charge(id: string, kind: 'PIX' | 'LINK'): Observable<Installment> {
    return this.http.post<Installment>(`${INSTALLMENTS}${id}/charge/`, { kind });
  }

  sendWhatsApp(id: string): Observable<void> {
    return this.http.post<void>(`${INSTALLMENTS}${id}/send-whatsapp/`, {});
  }

  mercadoPago(): Observable<MercadoPagoStatus> {
    return this.http.get<MercadoPagoStatus>(MP);
  }

  connectMercadoPago(accessToken: string): Observable<MercadoPagoStatus> {
    return this.http.put<MercadoPagoStatus>(MP, { access_token: accessToken });
  }

  disconnectMercadoPago(): Observable<MercadoPagoStatus> {
    return this.http.delete<MercadoPagoStatus>(MP);
  }
}
