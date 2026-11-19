export type PublicationStatus = 'NEW' | 'DONE' | 'IGNORED';

export const PUBLICATION_STATUS_LABELS: Record<PublicationStatus, string> = {
  NEW: 'Novas',
  DONE: 'Tratadas',
  IGNORED: 'Ignoradas',
};

export const UFS = [
  'AC',
  'AL',
  'AM',
  'AP',
  'BA',
  'CE',
  'DF',
  'ES',
  'GO',
  'MA',
  'MG',
  'MS',
  'MT',
  'PA',
  'PB',
  'PE',
  'PI',
  'PR',
  'RJ',
  'RN',
  'RO',
  'RR',
  'RS',
  'SC',
  'SE',
  'SP',
  'TO',
] as const;

export interface MonitoredOab {
  id: string;
  number: string;
  uf: string;
  lawyer_name: string;
  user_id: string | null;
  user_name: string;
  is_active: boolean;
  last_checked_at: string | null;
  fetched_until: string | null;
  last_error: string;
  new_count: number;
  created_at: string;
}

export interface MonitoredOabInput {
  number: string;
  uf: string;
  lawyer_name?: string;
  user_id?: string | null;
  is_active?: boolean;
}

export interface Publication {
  id: string;
  djen_id: number;
  cnj_number: string;
  cnj_formatted: string;
  case_id: string | null;
  tribunal: string;
  kind: string;
  document_type: string;
  orgao: string;
  classe: string;
  available_on: string;
  /** Texto puro (o servidor já tira o HTML). */
  text: string;
  link: string;
  recipients: string[];
  deadline_hints: string[];
  oab_label: string;
  status: PublicationStatus;
  handled_at: string | null;
  handled_by_name: string;
  created_at: string;
}
