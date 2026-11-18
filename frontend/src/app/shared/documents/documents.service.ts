import { HttpClient, HttpEvent } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { Page, listParams } from '../../core/http/page';
import { DocumentCategory, DocumentFilters, DocumentItem } from './documents.models';

const API = '/api/v1/documents/';

export interface UploadInput {
  file: File;
  client_id?: string | null;
  legal_case_id?: string | null;
  category: DocumentCategory;
  description?: string;
}

@Injectable({ providedIn: 'root' })
export class DocumentsService {
  private readonly http = inject(HttpClient);

  list(filters: DocumentFilters, pageIndex = 0, pageSize = 50): Observable<Page<DocumentItem>> {
    return this.http.get<Page<DocumentItem>>(API, {
      params: listParams({ ...filters }, pageIndex, pageSize),
    });
  }

  upload(input: UploadInput): Observable<HttpEvent<DocumentItem>> {
    const form = new FormData();
    form.append('file', input.file, input.file.name);
    form.append('category', input.category);
    if (input.client_id) form.append('client_id', input.client_id);
    if (input.legal_case_id) form.append('legal_case_id', input.legal_case_id);
    if (input.description) form.append('description', input.description);
    return this.http.post<DocumentItem>(API, form, { reportProgress: true, observe: 'events' });
  }

  update(
    id: string,
    body: Partial<Pick<DocumentItem, 'name' | 'category' | 'description'>>,
  ): Observable<DocumentItem> {
    return this.http.patch<DocumentItem>(`${API}${id}/`, body);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(`${API}${id}/`);
  }

  /** O arquivo vem com o token (não há link público); vira um blob local. */
  blob(id: string, inline = false): Observable<Blob> {
    return this.http.get(`${API}${id}/download/`, {
      params: inline ? { inline: '1' } : {},
      responseType: 'blob',
    });
  }

  /** Abre a prévia numa aba nova (PDF, imagem, áudio, vídeo). */
  open(doc: Pick<DocumentItem, 'id' | 'name' | 'can_preview'>): void {
    if (!doc.can_preview) {
      this.download(doc);
      return;
    }
    // A aba abre já (antes da resposta) para o navegador não bloquear como pop-up.
    const tab = window.open('', '_blank');
    this.blob(doc.id, true).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        if (tab) {
          tab.location.href = url;
        } else {
          window.location.assign(url);
        }
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      error: () => tab?.close(),
    });
  }

  download(doc: Pick<DocumentItem, 'id' | 'name'>): void {
    this.blob(doc.id).subscribe((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    });
  }

  /** URL local (blob:) para mostrar imagem/áudio dentro da página. Revogue ao destruir. */
  objectUrl(id: string): Observable<string> {
    return this.blob(id, true).pipe(map((blob) => URL.createObjectURL(blob)));
  }
}
