// Compare two tag lists as sets — reordering isn't a real edit. Assumes no
// duplicates within a list.
export function sameTags(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sb = new Set(b);
  return a.every((x) => sb.has(x));
}
