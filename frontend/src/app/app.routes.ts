import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth/auth.guards';

export const routes: Routes = [
  {
    path: 'login',
    canMatch: [guestGuard],
    title: 'Entrar · TramitAI',
    loadComponent: () => import('./features/auth/login/login').then((m) => m.Login),
  },
  {
    path: '',
    canMatch: [authGuard],
    loadComponent: () => import('./layout/shell/shell').then((m) => m.Shell),
    children: [
      {
        path: '',
        title: 'Início · TramitAI',
        loadComponent: () => import('./features/home/home').then((m) => m.Home),
      },
      {
        path: 'inbox',
        title: 'Conversas · TramitAI',
        loadComponent: () => import('./features/inbox/inbox/inbox').then((m) => m.Inbox),
      },
      {
        path: 'inbox/:id',
        title: 'Conversa · TramitAI',
        loadComponent: () => import('./features/inbox/inbox/inbox').then((m) => m.Inbox),
      },
      {
        path: 'aprovacoes',
        title: 'Aprovações · TramitAI',
        loadComponent: () =>
          import('./features/aprovacoes/approvals/approvals').then((m) => m.Approvals),
      },
      {
        path: 'clientes',
        loadChildren: () =>
          import('./features/clientes/clientes.routes').then((m) => m.CLIENTES_ROUTES),
      },
      {
        path: 'processos',
        loadChildren: () =>
          import('./features/processos/processos.routes').then((m) => m.PROCESSOS_ROUTES),
      },
      {
        path: 'configuracoes/termo',
        title: 'Termo de ciência · TramitAI',
        loadComponent: () =>
          import('./features/configuracoes/term-settings/term-settings').then(
            (m) => m.TermSettings,
          ),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
