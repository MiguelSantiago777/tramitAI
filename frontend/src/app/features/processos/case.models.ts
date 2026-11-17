export type CaseStatus = 'ACTIVE' | 'ARCHIVED';
export type CaseClientRole = 'AUTHOR' | 'DEFENDANT' | 'OTHER';

export interface CaseClient {
  client_id: string;
  client_name: string;
  role: CaseClientRole;
}

export interface LegalCase {
  id: string;
  cnj_number: string;
  cnj_formatted: string;
  tribunal: string;
  classe: string;
  assunto: string;
  orgao_julgador: string;
  responsible_id: string | null;
  responsible_name: string;
  status: CaseStatus;
  monitoring_enabled: boolean;
  last_checked_at: string | null;
  last_movement_at: string | null;
  notes: string;
  clients: CaseClient[];
  created_at: string;
  updated_at: string;
}

export interface LegalCaseInput {
  cnj_number: string;
  classe: string;
  assunto: string;
  orgao_julgador: string;
  responsible_id: string | null;
  status: CaseStatus;
  monitoring_enabled: boolean;
  notes: string;
  clients: { client_id: string; role: CaseClientRole }[];
}

export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  ACTIVE: 'Ativo',
  ARCHIVED: 'Arquivado',
};

export const CASE_ROLE_LABELS: Record<CaseClientRole, string> = {
  AUTHOR: 'Autor',
  DEFENDANT: 'Réu',
  OTHER: 'Outro',
};
