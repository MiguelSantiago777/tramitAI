export type ClientKind = 'PF' | 'PJ';
export type ClientStatus = 'LEAD' | 'ACTIVE' | 'ARCHIVED';
export type AcceptanceChannel = 'WHATSAPP' | 'IN_PERSON' | 'EMAIL' | 'OTHER';

export interface Client {
  id: string;
  kind: ClientKind;
  name: string;
  cpf_cnpj: string;
  phone: string;
  email: string;
  status: ClientStatus;
  notes: string;
  created_at: string;
  updated_at: string;
}

export type ClientInput = Omit<Client, 'id' | 'created_at' | 'updated_at'>;

export interface TermAcceptance {
  id: string;
  term_version: number;
  accepted_at: string;
  channel: AcceptanceChannel;
  evidence: string;
  recorded_by_name: string;
  created_at: string;
}

export const CLIENT_STATUS_LABELS: Record<ClientStatus, string> = {
  LEAD: 'Lead',
  ACTIVE: 'Ativo',
  ARCHIVED: 'Arquivado',
};

export const CLIENT_KIND_LABELS: Record<ClientKind, string> = {
  PF: 'Pessoa física',
  PJ: 'Pessoa jurídica',
};

export const CHANNEL_LABELS: Record<AcceptanceChannel, string> = {
  WHATSAPP: 'WhatsApp',
  IN_PERSON: 'Presencial',
  EMAIL: 'E-mail',
  OTHER: 'Outro',
};

export type NoteKind = 'NOTE' | 'CALL' | 'MEETING' | 'VISIT';

export const NOTE_KIND_LABELS: Record<NoteKind, string> = {
  NOTE: 'Anotação',
  CALL: 'Ligação',
  MEETING: 'Reunião',
  VISIT: 'Atendimento presencial',
};

export interface ClientNote {
  id: string;
  kind: NoteKind;
  body: string;
  legal_case_id: string | null;
  author_name: string;
  created_at: string;
}

export type TimelineType =
  'note' | 'task' | 'task_done' | 'event' | 'message' | 'case' | 'movement' | 'term';

export interface TimelineItem {
  id: string;
  type: TimelineType;
  at: string;
  title: string;
  body: string;
  meta: Record<string, string | null>;
}

export interface Timeline {
  results: TimelineItem[];
  next_before: string | null;
}
