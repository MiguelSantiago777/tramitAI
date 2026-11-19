import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type DraftKind = 'PETITION' | 'FEE_CONTRACT' | 'POWER' | 'DECLARATION' | 'OTHER';
export type DraftStatus = 'PENDING' | 'DONE' | 'ERROR';

export const DRAFT_KINDS: { value: DraftKind; label: string; hint: string }[] = [
  {
    value: 'PETITION',
    label: 'Petição',
    hint: 'Ex.: petição inicial de indenização por dano moral. Conte os fatos (datas, o que aconteceu), os pedidos e o valor da causa.',
  },
  {
    value: 'FEE_CONTRACT',
    label: 'Contrato de honorários',
    hint: 'Ex.: honorários para ação trabalhista, 30% de êxito. Se escolher os honorários cadastrados, os valores e parcelas entram sozinhos.',
  },
  {
    value: 'POWER',
    label: 'Procuração',
    hint: 'Ex.: procuração ad judicia et extra com poderes para receber e dar quitação.',
  },
  {
    value: 'DECLARATION',
    label: 'Declaração',
    hint: 'Ex.: declaração de hipossuficiência para pedir a justiça gratuita.',
  },
  { value: 'OTHER', label: 'Outro documento', hint: 'Descreva o documento que você precisa.' },
];

export interface DocumentDraft {
  id: string;
  kind: DraftKind;
  kind_label: string;
  title: string;
  client_id: string | null;
  legal_case_id: string | null;
  fee_agreement_id: string | null;
  status: DraftStatus;
  error_code: string;
  review_notes: string;
  missing_fields: string[];
  docx_id: string | null;
  pdf_id: string | null;
  created_at: string;
}

export interface DraftInput {
  kind: DraftKind;
  title: string;
  instructions: string;
  client_id?: string | null;
  legal_case_id?: string | null;
  fee_agreement_id?: string | null;
}

/** Minutas escritas pela Lia (Word e PDF salvos na pasta do cliente). */
@Injectable({ providedIn: 'root' })
export class DraftsService {
  private readonly http = inject(HttpClient);

  create(input: DraftInput): Observable<DocumentDraft> {
    return this.http.post<DocumentDraft>('/api/v1/document-drafts/', input);
  }

  get(id: string): Observable<DocumentDraft> {
    return this.http.get<DocumentDraft>(`/api/v1/document-drafts/${id}/`);
  }
}
