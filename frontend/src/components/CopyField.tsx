import { useState } from 'react';
import { useI18n } from '../i18n';
import { writeToClipboard } from '../utils/clipboard';

/** Read-only value paired with a Copy button. The input is fully selectable
 *  (and selects itself on focus) so a credential like a temporary password can
 *  be copied in one tap instead of character by character. */
export default function CopyField({ value, label }: { value: string; label?: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  async function copy() {
    await writeToClipboard(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
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
