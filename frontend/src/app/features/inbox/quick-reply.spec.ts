import { fillQuickReply } from './inbox.models';

describe('fillQuickReply', () => {
  it('troca {nome} pelo primeiro nome', () => {
    expect(fillQuickReply('Olá, {nome}! Tudo bem, {nome}?', 'Maria da Silva')).toBe(
      'Olá, Maria! Tudo bem, Maria?',
    );
  });

  it('sem nome usa uma saudação neutra', () => {
    expect(fillQuickReply('Olá, {nome}!', '')).toBe('Olá, tudo bem!');
  });
});
