import { ChangeDetectionStrategy, Component } from '@angular/core';

/** Moldura das telas sem login: painel da marca à esquerda e o conteúdo à direita. */
@Component({
  selector: 'app-auth-layout',
  template: `
    <main class="auth">
      <section class="auth__brand" aria-hidden="true">
        <div class="auth__logo">
          <span class="auth__mark">T</span>
          <span>TramitAI</span>
        </div>
        <div class="auth__pitch">
          <h2>Seu escritório atendendo no WhatsApp, sem perder o controle.</h2>
          <ul>
            <li>
              <span class="icon">forum</span>
              A Vera faz a triagem das mensagens e escreve a resposta.
            </li>
            <li>
              <span class="icon">gavel</span>
              Andamentos do tribunal explicados em português simples.
            </li>
            <li>
              <span class="icon">task_alt</span>
              Nada sai para o cliente sem a aprovação do advogado.
            </li>
          </ul>
        </div>
        <p class="auth__foot">Dados protegidos conforme a LGPD.</p>
      </section>

      <section class="auth__panel">
        <div class="auth__box">
          <div class="auth__logo auth__logo--mobile">
            <span class="auth__mark">T</span>
            <span>TramitAI</span>
          </div>
          <ng-content />
        </div>
      </section>
    </main>
  `,
  styleUrl: './auth-layout.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuthLayout {}
