export type CaseStatus = 'ACTIVE' | 'ARCHIVED';
export type CaseClientRole = 'AUTHOR' | 'DEFENDANT' | 'OTHER';
export type SyncStatus = 'NEVER' | 'OK' | 'NOT_FOUND' | 'ERROR';
export type MovementNotification = 'BASELINE' | 'PENDING' | 'NOTIFIED' | 'SKIPPED';

export interface CaseMovement {
  id: string;
  name: string;
  code: number | null;
  complements: string[];
  grau: string;
  occurred_at: string;
  notification: MovementNotification;
}

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
  sync_status: SyncStatus;
  sync_error: string;
  pending_movements: number;
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

export const SYNC_STATUS_LABELS: Record<SyncStatus, string> = {
  NEVER: 'Ainda não consultado',
  OK: 'Atualizado',
  NOT_FOUND: 'Não encontrado no DataJud',
  ERROR: 'Erro na última consulta',
};

export const NOTIFICATION_LABELS: Record<MovementNotification, string> = {
  BASELINE: 'Histórico',
  PENDING: 'Aviso aguardando aprovação',
  NOTIFIED: 'Cliente avisado',
  SKIPPED: 'Sem aviso',
};
