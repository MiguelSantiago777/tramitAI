export type DocumentCategory =
  'PESSOAL' | 'COMPROVANTE' | 'CONTRATO' | 'PECA' | 'DECISAO' | 'PROVA' | 'WHATSAPP' | 'OUTRO';

export interface DocumentItem {
  id: string;
  name: string;
  content_type: string;
  size: number;
  category: DocumentCategory;
  category_label: string;
  description: string;
  source: 'UPLOAD' | 'WHATSAPP';
  client_id: string | null;
  client_name: string;
  legal_case_id: string | null;
  case_number: string;
  conversation_id: string | null;
  message_id: string | null;
  uploaded_by_name: string;
  can_preview: boolean;
  created_at: string;
}

export interface DocumentFilters {
  client?: string;
  legal_case?: string;
  conversation?: string;
  category?: DocumentCategory | '';
  q?: string;
}

export const CATEGORY_LABELS: Record<DocumentCategory, string> = {
  PESSOAL: 'Documento pessoal',
  COMPROVANTE: 'Comprovante',
  CONTRATO: 'Contrato / procuração',
  PECA: 'Peça processual',
  DECISAO: 'Decisão / sentença',
  PROVA: 'Prova',
  WHATSAPP: 'Recebido no WhatsApp',
  OUTRO: 'Outro',
};

/** Extensões aceitas no upload (o backend confere de novo). */
export const ACCEPTED_FILES =
  '.pdf,.jpg,.jpeg,.png,.webp,.heic,.gif,.doc,.docx,.xls,.xlsx,.odt,.ods,.rtf,.txt,.csv,' +
  '.mp3,.ogg,.opus,.m4a,.wav,.mp4,.mov,.zip';

export const MAX_FILE_MB = 25;

export function fileIcon(contentType: string): string {
  if (contentType.startsWith('image/')) return 'image';
  if (contentType.startsWith('audio/')) return 'mic';
  if (contentType.startsWith('video/')) return 'movie';
  if (contentType === 'application/pdf') return 'picture_as_pdf';
  if (contentType.includes('sheet') || contentType.includes('excel') || contentType === 'text/csv')
    return 'table_chart';
  return 'description';
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`;
}
