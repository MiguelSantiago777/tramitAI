import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class PasswordService {
  private readonly http = inject(HttpClient);

  /** Pede o e-mail com o link. A API responde igual exista ou não a conta. */
  requestReset(email: string): Observable<void> {
    return this.http.post<void>('/api/v1/auth/password-reset/', { email });
  }

  confirmReset(uid: string, token: string, password: string): Observable<void> {
    return this.http.post<void>('/api/v1/auth/password-reset/confirm/', { uid, token, password });
  }
}
