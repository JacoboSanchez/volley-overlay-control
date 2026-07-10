import { Fragment, useState } from 'react';
import { useI18n } from '../i18n';
import { writeToClipboard } from '../utils/clipboard';

/** Split *value* after each URI separator (``/ ? & =``) so the wrapping block
 *  can prefer those as line-break points (via ``<wbr>``): the URL then wraps
 *  along its structure — origin / path / query — instead of mid-token.
 *  ``overflow-wrap: anywhere`` remains the fallback for a segment longer than
 *  the line (e.g. a very long capability token). */
function uriSegments(value: string): string[] {
  const segments: string[] = [];
  let current = '';
  for (const ch of value) {
    current += ch;
    if (ch === '/' || ch === '?' || ch === '&' || ch === '=') {
      segments.push(current);
      current = '';
    }
  }
  if (current) segments.push(current);
  return segments;
}

/** Select every character of *el* — the block-element equivalent of
 *  ``input.select()``, so a tap still grabs the whole value for manual copy. */
function selectContents(el: HTMLElement) {
  const range = document.createRange();
  range.selectNodeContents(el);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}

/** Read-only value paired with a Copy button. The value is fully selectable
 *  (and selects itself on focus) so a credential like a temporary password can
 *  be copied in one tap instead of character by character.
 *
 *  ``multiline`` swaps the one-line input for a wrapping block: a share URL on
 *  a portrait phone shows only its first characters inside an input, hiding
 *  which link it actually is — the block wraps so the whole URL stays visible. */
export default function CopyField({
  value,
  label,
  multiline = false,
}: {
  value: string;
  label?: string;
  multiline?: boolean;
}) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  async function copy() {
    await writeToClipboard(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (multiline) {
    // Icon-only copy control (the pattern LinkRow already uses on the board):
    // a "Copy" text button next to a three-line URL reads as a competing
    // action and eats a third of a portrait phone's width.
    return (
      <span className="acc-copy acc-copy--multiline">
        <span
          className="acc-copy-value"
          role="textbox"
          aria-readonly="true"
          tabIndex={0}
          aria-label={label}
          onFocus={(e) => selectContents(e.currentTarget)}
        >
          {uriSegments(value).map((segment, i) => (
            <Fragment key={i}>
              {i > 0 && <wbr />}
              {segment}
            </Fragment>
          ))}
        </span>
        <button
          type="button"
          className="acc-iconbtn acc-copy-iconbtn"
          title={t('acc.common.copy')}
          aria-label={t('acc.common.copy')}
          onClick={copy}
        >
          <span className="material-icons" aria-hidden="true">
            {copied ? 'check' : 'content_copy'}
          </span>
        </button>
      </span>
    );
  }

  return (
    <span className="acc-copy">
      <input
        className="acc-input acc-copy-input"
        readOnly
        value={value}
        aria-label={label}
        onFocus={(e) => e.currentTarget.select()}
      />
      <button type="button" className="acc-btn secondary" onClick={copy}>
        {copied ? t('acc.common.copied') : t('acc.common.copy')}
      </button>
    </span>
  );
}
