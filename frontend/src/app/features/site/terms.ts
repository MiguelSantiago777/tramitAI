import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * Termos de uso e privacidade (versão inicial). REVISAR com assessoria jurídica antes de
 * divulgar: dados do controlador, foro e prazos de retenção precisam ser confirmados.
 */
@Component({
  selector: 'app-terms',
  imports: [RouterLink],
  template: `
    <article class="terms">
      <a routerLink="/conheca">← TramitAI</a>
      <h1>Termos de uso e política de privacidade</h1>
      <p class="muted">Versão de 18/11/2026.</p>

      <h2>1. O serviço</h2>
      <p>
        O TramitAI é um sistema para escritórios de advocacia organizarem atendimento por WhatsApp,
        processos, agenda, documentos e honorários. A assistente virtual (Vera) sugere respostas; o
        envio ao cliente depende da aprovação de um usuário do escritório.
      </p>

      <h2>2. Responsabilidades</h2>
      <p>
        O escritório é o controlador dos dados dos seus clientes (LGPD) e responsável pelo conteúdo
        enviado e pela orientação jurídica. O TramitAI atua como operador, tratando os dados apenas
        para prestar o serviço contratado. A IA não dá orientação jurídica.
      </p>

      <h2>3. WhatsApp</h2>
      <p>
        A conexão do WhatsApp pode usar a API oficial da Meta ou a conexão pelo WhatsApp Web. Na
        segunda opção, o uso fica sujeito às regras do WhatsApp, que pode restringir números com uso
        considerado abusivo (como envio em massa). O escritório decide qual opção usar.
      </p>

      <h2>4. Dados e segurança</h2>
      <p>
        Os dados ficam em servidor no Brasil, com acesso restrito por escritório, backup diário
        criptografado e registro de auditoria. Segredos (como tokens de integração) são guardados
        cifrados. O conteúdo das conversas não é usado para outra finalidade que não a do serviço.
      </p>
      <p>
        Conteúdo enviado à IA é processado por provedor contratado pelo TramitAI apenas para gerar a
        sugestão de resposta, e somente depois do aceite do termo de ciência pelo cliente final.
      </p>

      <h2>5. Assinatura e cancelamento</h2>
      <p>
        Após o teste grátis, o uso depende de assinatura mensal paga pelo Mercado Pago. O
        cancelamento pode ser feito a qualquer momento; o acesso segue até o fim do período pago.
        Após o término, os dados ficam disponíveis para exportação por 30 dias, mediante pedido, e
        depois são excluídos, salvo obrigação legal de guarda.
      </p>

      <h2>6. Google Agenda</h2>
      <p>
        Se um usuário conectar o Google Agenda, o TramitAI usa o acesso autorizado (escopo
        <em>calendar.events</em>) apenas para: (a) criar, alterar e cancelar no Google Agenda desse
        usuário os compromissos que ele ou o escritório marcam no TramitAI; e (b) consultar o
        horário de início e fim dos compromissos já existentes, para não oferecer horários ocupados.
        Título, descrição, convidados e demais detalhes dos compromissos do Google não são lidos nem
        armazenados. Guardamos apenas o e-mail da conta conectada, a autorização (cifrada) e os
        intervalos de horário ocupados dos próximos 15 dias.
      </p>
      <p>
        Os dados do Google não são vendidos, não são usados para publicidade, não são usados para
        treinar modelos de inteligência artificial e não são compartilhados com terceiros. O usuário
        pode desconectar a qualquer momento na tela Agenda; a autorização é revogada e os dados
        guardados são apagados.
      </p>
      <p>
        O uso e a transferência, para qualquer outro aplicativo, de informações recebidas das APIs
        do Google seguirão a
        <a
          href="https://developers.google.com/terms/api-services-user-data-policy"
          target="_blank"
          rel="noopener"
          >Política de Dados do Usuário dos Serviços de API do Google</a
        >, incluindo os requisitos de Uso Limitado.
      </p>

      <h2>7. Contato</h2>
      <p>Dúvidas e pedidos sobre dados pessoais: pelo e-mail de suporte informado no sistema.</p>
    </article>
  `,
  styles: `
    .terms {
      max-width: 760px;
      margin: 0 auto;
      padding: 32px 20px 64px;
      line-height: 1.65;
    }
    h2 {
      margin-top: 28px;
      font-size: 1.15rem;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Terms {}
