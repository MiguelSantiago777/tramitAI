import { Routes } from '@angular/router';

export const PROCESSOS_ROUTES: Routes = [
  {
    path: '',
    title: 'Processos · TramitAI',
    loadComponent: () => import('./case-list/case-list').then((m) => m.CaseList),
  },
  {
    path: 'novo',
    title: 'Novo processo · TramitAI',
    loadComponent: () => import('./case-form/case-form').then((m) => m.CaseForm),
  },
  {
    path: ':id',
    title: 'Processo · TramitAI',
    loadComponent: () => import('./case-form/case-form').then((m) => m.CaseForm),
  },
];
