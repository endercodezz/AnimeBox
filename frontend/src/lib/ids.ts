/**
 * Mirror of backend `canonical_id`: `<source>:<url-quoted key>`.
 * Route params arrive decoded by the router (`animego:/anime/x`), API data is canonical
 * (`animego:%2Fanime%2Fx`); normalise before comparing or sending.
 */
export function canonicalId(id: string): string {
  const index = id.indexOf(':')
  if (index <= 0) return id
  const source = id.slice(0, index)
  let key = id.slice(index + 1)
  try {
    key = decodeURIComponent(key)
  } catch {
    /* already decoded and contains a bare '%' */
  }
  // encodeURIComponent leaves !'()* unescaped; Python's quote(safe='') escapes them.
  const quoted = encodeURIComponent(key).replace(/[!'()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`)
  return `${source}:${quoted}`
}
