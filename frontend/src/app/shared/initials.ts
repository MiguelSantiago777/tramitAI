/** Iniciais para avatar: "Maria da Silva" → "MS"; "joana.lima@x" → "JL". */
export function initialsOf(name: string): string {
  const clean = name
    .split('@')[0]
    .replace(/[._-]+/g, ' ')
    .trim();
  const parts = clean.split(/\s+/).filter((p) => /\p{L}/u.test(p));
  if (parts.length === 0) {
    return '?';
  }
  const first = parts[0][0] ?? '';
  const last = parts.length > 1 ? (parts[parts.length - 1][0] ?? '') : '';
  return (first + last).toUpperCase();
}
