import {
  formatCnj,
  formatDocument,
  formatPhone,
  isValidCnj,
  isValidCnpj,
  isValidCpf,
  normalizeBrPhone,
} from './br';

// Mesmos exemplos dos testes do backend (apps/core/tests/test_br.py e processos/tests/test_cnj.py).
describe('validadores BR', () => {
  it('CPF', () => {
    expect(isValidCpf('529.982.247-25')).toBe(true);
    expect(isValidCpf('529.982.247-24')).toBe(false);
    expect(isValidCpf('111.111.111-11')).toBe(false);
  });

  it('CNPJ numérico e alfanumérico', () => {
    expect(isValidCnpj('11.222.333/0001-81')).toBe(true);
    expect(isValidCnpj('12.ABC.345/01DE-35')).toBe(true);
    expect(isValidCnpj('12abc34501de35')).toBe(true);
    expect(isValidCnpj('11.222.333/0001-82')).toBe(false);
    expect(isValidCnpj('12.ABC.345/01DE-36')).toBe(false);
  });

  it('telefone', () => {
    expect(normalizeBrPhone('(21) 99876-5432')).toBe('+5521998765432');
    expect(normalizeBrPhone('+55 21 3456-7890')).toBe('+552134567890');
    expect(normalizeBrPhone('(21) 89876-5432')).toBeNull();
    expect(normalizeBrPhone('99876-5432')).toBeNull();
  });

  it('número CNJ (módulo 97)', () => {
    expect(isValidCnj('0801234-39.2024.8.19.0001')).toBe(true);
    expect(isValidCnj('08012343920248190001')).toBe(true);
    expect(isValidCnj('0801234-40.2024.8.19.0001')).toBe(false);
    expect(isValidCnj('0801234-39.2024.8.19.000')).toBe(false);
  });

  it('formatação', () => {
    expect(formatCnj('08012343920248190001')).toBe('0801234-39.2024.8.19.0001');
    expect(formatDocument('52998224725')).toBe('529.982.247-25');
    expect(formatDocument('12ABC34501DE35')).toBe('12.ABC.345/01DE-35');
    expect(formatPhone('+5521998765432')).toBe('(21) 99876-5432');
    expect(formatPhone('+552134567890')).toBe('(21) 3456-7890');
  });
});
