/**
 * How long a server action keeps its loading state visible, at minimum.
 *
 * The Demo fixtures answer almost instantly, so a completed step flashes past
 * and reads as a hardcoded result rather than a real call. This only paces the
 * UI: it never changes, delays or reorders what the server returned, and
 * failures surface immediately.
 */
export const minimumActionMs = import.meta.env.MODE === 'test' ? 0 : 2_000
