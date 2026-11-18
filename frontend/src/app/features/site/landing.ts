import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';

import { BillingService } from '../assinatura/billing.service';
import { money } from '../financeiro/financeiro.models';

/** Página pública de apresentação (quem ainda não é cliente). */
@Component({
  selector: 'app-landing',
  imports: [MatButtonModule, RouterLink],
  template: `
    <div class="site">
      <header class="nav">
        <a class="logo" routerLink="/conheca"><span class="mark">T</span> TramitAI</a>
        <span class="spacer"></span>
        <a mat-button routerLink="/login">Entrar</a>
        <a mat-flat-button routerLink="/cadastro">Teste grátis</a>
      </header>

      <section class="hero">
        <h1>O WhatsApp do seu escritório atendendo bem, sem você perder o controle.</h1>
        <p class="sub">
          A Lia faz a triagem das mensagens, explica andamentos em português simples e escreve as
          respostas. Nada sai para o cliente sem a aprovação do advogado.
        </p>
        <div class="cta">
          <a mat-flat-button routerLink="/cadastro">Começar teste grátis de 14 dias</a>
          <span class="muted">Sem cartão para testar.</span>
        </div>
      </section>

      <section class="features">
        @for (f of features; track f.title) {
          <article class="feature">
            <span class="icon">{{ f.icon }}</span>
            <h3>{{ f.title }}</h3>
            <p>{{ f.text }}</p>
          </article>
        }
      </section>

      <section class="pricing">
        <h2>Preço simples</h2>
        @for (p of plans(); track p.code) {
          <article class="plan">
            <h3>{{ p.name }}</h3>
            <p class="price">{{ fmt(p.price) }}<span>/mês</span></p>
            <p>{{ p.description }}</p>
            <a mat-flat-button routerLink="/cadastro">Testar 14 dias grátis</a>
          </article>
        }
        <p class="muted small">Assinatura mensal pelo Mercado Pago. Cancele quando quiser.</p>
      </section>

      <footer class="foot">
        <span>TramitAI · Dados protegidos conforme a LGPD</span>
        <a routerLink="/termos">Termos de uso e privacidade</a>
      </footer>
    </div>
  `,
  styles: `
    .site {
      max-width: 1080px;
      margin: 0 auto;
      padding: 0 20px 40px;
    }
    .nav {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 16px 0;
    }
    .spacer {
      flex: 1;
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 700;
      font-size: 1.15rem;
      text-decoration: none;
      color: inherit;
    }
    .mark {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      color: #fff;
      background: var(--tm-brand-gradient);
    }
    .hero {
      padding: 56px 0 40px;
      max-width: 760px;
    }
    .hero h1 {
      font-size: clamp(1.8rem, 4vw, 2.8rem);
      line-height: 1.15;
      margin: 0 0 16px;
    }
    .sub {
      font-size: 1.1rem;
      line-height: 1.6;
      color: var(--mat-sys-on-surface-variant);
    }
    .cta {
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 24px;
    }
    .features {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin: 24px 0 48px;
    }
    .feature {
      padding: 20px;
      border-radius: var(--tm-radius);
      background: var(--mat-sys-surface-container-low);
    }
    .feature .icon {
      font-size: 28px;
      color: var(--mat-sys-primary);
    }
    .feature h3 {
      margin: 8px 0 6px;
    }
    .feature p {
      margin: 0;
      line-height: 1.5;
      color: var(--mat-sys-on-surface-variant);
    }
    .pricing {
      text-align: center;
      display: grid;
      justify-items: center;
      gap: 12px;
    }
    .plan {
      padding: 24px 32px;
      border-radius: var(--tm-radius);
      box-shadow: var(--tm-shadow);
      max-width: 380px;
    }
    .price {
      font-size: 2.2rem;
      font-weight: 700;
      margin: 8px 0;
    }
    .price span {
      font-size: 1rem;
      font-weight: 400;
    }
    .foot {
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 48px;
      color: var(--mat-sys-on-surface-variant);
      font-size: 0.9rem;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Landing {
  readonly plans = toSignal(
    inject(BillingService)
      .plans()
      .pipe(catchError(() => of([]))),
    { initialValue: [] },
  );

  readonly features = [
    {
      icon: 'forum',
      title: 'Triagem no WhatsApp',
      text: 'A Lia entende o que o cliente quer, separa o urgente e deixa a resposta pronta.',
    },
    {
      icon: 'gavel',
      title: 'Andamentos explicados',
      text: 'Monitora os processos no tribunal e avisa o cliente em português simples.',
    },
    {
      icon: 'verified_user',
      title: 'Você aprova tudo',
      text: 'Nenhuma mensagem sai sem o OK do advogado. Termo de ciência de IA incluído.',
    },
    {
      icon: 'view_kanban',
      title: 'Funil de novos clientes',
      text: 'Quem chega pelo WhatsApp entra no funil até virar contrato.',
    },
    {
      icon: 'folder_open',
      title: 'Documentos organizados',
      text: 'O que o cliente manda no WhatsApp vai direto para a pasta dele.',
    },
    {
      icon: 'payments',
      title: 'Honorários com Pix',
      text: 'Parcelas, Pix e link do Mercado Pago, baixa automática e lembrete de vencimento.',
    },
  ];

  fmt(price: string): string {
    return money(price);
  }
}
