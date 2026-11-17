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
    path: 'esqueci-senha',
    canMatch: [guestGuard],
    title: 'Esqueci minha senha · TramitAI',
    loadComponent: () =>
      import('./features/auth/forgot-password/forgot-password').then((m) => m.ForgotPassword),
  },
  {
    path: 'redefinir-senha',
    canMatch: [guestGuard],
    title: 'Criar senha nova · TramitAI',
    loadComponent: () =>
      import('./features/auth/reset-password/reset-password').then((m) => m.ResetPassword),
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
        path: 'funil',
        title: 'Funil · TramitAI',
        loadComponent: () => import('./features/funil/board/board').then((m) => m.Board),
      },
      {
        path: 'configuracoes/etiquetas',
        title: 'Etiquetas · TramitAI',
        loadComponent: () =>
          import('./features/configuracoes/tags/tags-page').then((m) => m.TagsPage),
      },
      {
        path: 'configuracoes/respostas',
        title: 'Respostas prontas · TramitAI',
        loadComponent: () =>
          import('./features/configuracoes/quick-replies/quick-replies-page').then(
            (m) => m.QuickRepliesPage,
          ),
      },
      {
        path: 'tarefas',
        title: 'Tarefas · TramitAI',
        loadComponent: () =>
          import('./features/agenda/tasks-page/tasks-page').then((m) => m.TasksPage),
      },
      {
        path: 'agenda',
        title: 'Agenda · TramitAI',
        loadComponent: () =>
          import('./features/agenda/agenda-page/agenda-page').then((m) => m.AgendaPage),
      },
      {
        path: 'configuracoes/equipe',
        title: 'Equipe · TramitAI',
        loadComponent: () => import('./features/configuracoes/team/team').then((m) => m.Team),
      },
      {
        path: 'configuracoes/escritorio',
        title: 'Configurações · TramitAI',
        loadComponent: () =>
          import('./features/configuracoes/office-settings/office-settings').then(
            (m) => m.OfficeSettingsPage,
          ),
      },
      {
        path: 'configuracoes/whatsapp',
        title: 'WhatsApp · TramitAI',
        loadComponent: () =>
          import('./features/configuracoes/whatsapp-connection/whatsapp-connection').then(
            (m) => m.WhatsAppConnectionPage,
          ),
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
