import { useState } from 'react';
import { useI18n } from '../i18n';
import { writeToClipboard } from '../utils/clipboard';

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

  return (
    <span className={`acc-copy${multiline ? ' acc-copy--multiline' : ''}`}>
      {multiline ? (
        <span
          className="acc-copy-value"
          role="textbox"
          aria-readonly="true"
          tabIndex={0}
          aria-label={label}
          onFocus={(e) => selectContents(e.currentTarget)}
        >
          {value}
        </span>
      ) : (
        <input
          className="acc-input acc-copy-input"
          readOnly
          value={value}
          aria-label={label}
          onFocus={(e) => e.currentTarget.select()}
        />
      )}
      <button type="button" className="acc-btn secondary" onClick={copy}>
        {copied ? t('acc.common.copied') : t('acc.common.copy')}
      </button>
    </span>
  );
}
