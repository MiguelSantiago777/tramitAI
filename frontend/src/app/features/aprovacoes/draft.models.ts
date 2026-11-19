export type DraftOrigin =
  'AI_REPLY' | 'TERM_REQUEST' | 'MOVEMENT_UPDATE' | 'EVENT_REMINDER' | 'PAYMENT_REMINDER';
export type DraftStatus = 'DRAFT' | 'APPROVED' | 'AWAITING' | 'SENT' | 'REJECTED' | 'FAILED';
export type Urgency = 'low' | 'normal' | 'high' | '';

export interface AuditEntry {
  action: string;
  actor_type: 'USER' | 'SYSTEM' | 'AI';
  actor_name: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface DraftMovement {
  id: string;
  name: string;
  complements: string[];
  occurred_at: string;
}

export interface Draft {
  id: string;
  conversation_id: string;
  contact_name: string;
  phone: string;
  client_id: string | null;
  client_name: string;
  origin: DraftOrigin;
  status: DraftStatus;
  generated_body: string;
  final_body: string;
  original_ai_text: string;
  intent: string;
  urgency: Urgency;
  needs_lawyer: boolean;
  summary: string;
  guardrail_flags: string[];
  source_text: string;
  window_open: boolean;
  decided_by_name: string;
  decided_at: string | null;
  rejection_reason: string;
  failure_detail: string;
  sent_message_status: string;
  legal_case_id: string | null;
  case_number: string;
  movements: DraftMovement[];
  client_relevant: boolean | null;
  template_text: string;
  template_status: string;
  created_at: string;
  history?: AuditEntry[];
}

export const ORIGIN_LABELS: Record<DraftOrigin, string> = {
  AI_REPLY: 'Resposta da Vera',
  TERM_REQUEST: 'Termo de ciência',
  MOVEMENT_UPDATE: 'Andamento do processo',
  EVENT_REMINDER: 'Lembrete de compromisso',
  PAYMENT_REMINDER: 'Lembrete de pagamento',
};

export const DRAFT_STATUS_LABELS: Record<DraftStatus, string> = {
  DRAFT: 'Aguardando aprovação',
  APPROVED: 'Aprovada, enviando…',
  AWAITING: 'Aviso enviado, aguardando o cliente responder',
  SENT: 'Enviada',
  REJECTED: 'Rejeitada',
  FAILED: 'Falhou no envio',
};

export const INTENT_LABELS: Record<string, string> = {
  case_status: 'Andamento de processo',
  new_matter: 'Caso novo',
  documents: 'Documentos',
  scheduling: 'Agendamento',
  fees: 'Honorários',
  greeting: 'Cumprimento',
  other: 'Outro assunto',
};

export const URGENCY_LABELS: Record<string, string> = {
  high: 'Urgente',
  normal: 'Normal',
  low: 'Baixa',
};

export const FLAG_LABELS: Record<string, string> = {
  unknown_case_number: 'citou número de processo que não está no cadastro',
  unknown_date: 'citou data que não está no cadastro',
  legal_citation: 'citou lei, artigo ou jurisprudência',
  deadline: 'falou de prazo',
};
