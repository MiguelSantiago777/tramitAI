export type ConversationStatus = 'OPEN' | 'CLOSED';
export type MessageDirection = 'IN' | 'OUT';
export type MessageStatus =
  'RECEIVED' | 'QUEUED' | 'SENDING' | 'SENT' | 'DELIVERED' | 'READ' | 'FAILED';

export interface LastMessage {
  direction: MessageDirection;
  type: string;
  status: MessageStatus;
  preview: string;
}

export interface Conversation {
  id: string;
  wa_id: string;
  phone: string;
  contact_name: string;
  client_id: string | null;
  client_name: string;
  status: ConversationStatus;
  last_inbound_at: string | null;
  last_message_at: string | null;
  unread_count: number;
  window_open: boolean;
  window_expires_at: string | null;
  last_message: LastMessage | null;
}

export interface Message {
  id: string;
  direction: MessageDirection;
  type: string;
  body: string;
  status: MessageStatus;
  error_detail: string;
  sent_by_name: string;
  wa_timestamp: string | null;
  delivered_at: string | null;
  read_at: string | null;
  created_at: string;
}

export const MEDIA_LABELS: Record<string, string> = {
  image: 'Imagem',
  audio: 'Áudio',
  video: 'Vídeo',
  document: 'Documento',
  sticker: 'Figurinha',
  location: 'Localização',
  other: 'Mensagem não suportada',
};

export const OUTBOUND_STATUS_LABELS: Partial<Record<MessageStatus, string>> = {
  QUEUED: 'Enviando…',
  SENDING: 'Enviando…',
  SENT: 'Enviada ✓',
  DELIVERED: 'Entregue ✓✓',
  READ: 'Lida ✓✓',
  FAILED: 'Falhou',
};
