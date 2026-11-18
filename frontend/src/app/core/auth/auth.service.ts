import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, finalize, firstValueFrom, map, shareReplay, tap } from 'rxjs';

import { LoginResponse, Session } from './auth.models';
import { tokenStorage } from './token-storage';

export const AUTH_URLS = {
  login: '/api/v1/auth/login/',
  refresh: '/api/v1/auth/refresh/',
  me: '/api/v1/auth/me/',
  signup: '/api/v1/auth/signup/',
} as const;

export interface SignupInput {
  office_name: string;
  full_name: string;
  email: string;
  password: string;
  accept_terms: boolean;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly sessionState = signal<Session | null>(null);
  private refreshInFlight$: Observable<string> | null = null;

  readonly session = this.sessionState.asReadonly();
  readonly isAuthenticated = computed(() => this.sessionState() !== null);

  get accessToken(): string | null {
    return tokenStorage.access;
  }

  get hasRefreshToken(): boolean {
    return tokenStorage.refresh !== null;
  }

  login(email: string, password: string, tenantId?: string): Observable<Session> {
    return this.http
      .post<LoginResponse>(AUTH_URLS.login, { email, password, tenant_id: tenantId ?? null })
      .pipe(
        tap((res) => {
          tokenStorage.save(res.access, res.refresh);
          this.sessionState.set(res.session);
        }),
        map((res) => res.session),
      );
  }

  /** Cadastro do escritório (teste grátis): já volta logado. */
  signup(input: SignupInput): Observable<Session> {
    return this.http.post<LoginResponse>(AUTH_URLS.signup, input).pipe(
      tap((res) => {
        tokenStorage.save(res.access, res.refresh);
        this.sessionState.set(res.session);
      }),
      map((res) => res.session),
    );
  }

  /** Renova o access token. Chamadas simultâneas compartilham o mesmo request. */
  refresh(): Observable<string> {
    this.refreshInFlight$ ??= this.http
      .post<{ access: string; refresh?: string }>(AUTH_URLS.refresh, {
        refresh: tokenStorage.refresh,
      })
      .pipe(
        tap((res) => tokenStorage.save(res.access, res.refresh)),
        map((res) => res.access),
        finalize(() => (this.refreshInFlight$ = null)),
        shareReplay(1),
      );
    return this.refreshInFlight$;
  }

  /** Recupera a sessão no carregamento da página, se houver token salvo. */
  async restoreSession(): Promise<void> {
    if (!tokenStorage.access) {
      return;
    }
    try {
      this.sessionState.set(await firstValueFrom(this.http.get<Session>(AUTH_URLS.me)));
    } catch {
      this.logout();
    }
  }

  logout(): void {
    tokenStorage.clear();
    this.sessionState.set(null);
  }
}
