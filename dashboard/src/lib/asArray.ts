// Guard for query data that *should* be an array but might not be (a backend
// error object, null, a wrapped payload). `?? []` only covers null/undefined —
// a truthy non-array still reaches `.map`/`.filter`/`.slice` and throws. Use
// this anywhere a list is rendered straight from a response.
export const asArray = <T>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
