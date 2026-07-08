/** Max icon display-name length — mirrors the backend `icons.name` column. */
export const ICON_NAME_MAX = 120;

/** Prefill an icon name from an uploaded file's name: extension stripped,
 *  trimmed, and truncated to the column limit so a long filename doesn't
 *  bounce off the server's 120-char validation. */
export function prefillIconName(filename: string): string {
  return filename
    .replace(/\.[^.]+$/, '')
    .trim()
    .slice(0, ICON_NAME_MAX);
}
