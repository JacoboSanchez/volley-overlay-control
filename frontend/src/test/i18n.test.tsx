import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { I18nProvider, useI18n } from '../i18n';

function TestConsumer() {
  const { t, lang, setLanguage, languages } = useI18n();
  return (
    <div>
      <span data-testid="lang">{lang}</span>
      <span data-testid="title">{t('app.title')}</span>
      <span data-testid="param">{t('dialog.setScore', { team: 1 })}</span>
      <span data-testid="languages">{languages.join(',')}</span>
      <button onClick={() => setLanguage('es')} data-testid="switch-es">ES</button>
      <button onClick={() => setLanguage('en')} data-testid="switch-en">EN</button>
    </div>
  );
}

describe('i18n', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults to English', () => {
    render(<I18nProvider><TestConsumer /></I18nProvider>);
    expect(screen.getByTestId('lang')).toHaveTextContent('en');
    expect(screen.getByTestId('title')).toHaveTextContent('Volley Scoreboard');
  });

  it('interpolates parameters', () => {
    render(<I18nProvider><TestConsumer /></I18nProvider>);
    expect(screen.getByTestId('param')).toHaveTextContent('Set score — Team 1');
  });

  it('switches to Spanish', () => {
    render(<I18nProvider><TestConsumer /></I18nProvider>);
    fireEvent.click(screen.getByTestId('switch-es'));
    expect(screen.getByTestId('lang')).toHaveTextContent('es');
    expect(screen.getByTestId('title')).toHaveTextContent('Marcador');
  });

  it('persists language to localStorage', () => {
    render(<I18nProvider><TestConsumer /></I18nProvider>);
    fireEvent.click(screen.getByTestId('switch-es'));
    expect(localStorage.getItem('volley_lang')).toBe('es');
  });

  it('restores language from localStorage', () => {
    localStorage.setItem('volley_lang', 'es');
    render(<I18nProvider><TestConsumer /></I18nProvider>);
    expect(screen.getByTestId('lang')).toHaveTextContent('es');
  });

  it('provides available languages', () => {
    render(<I18nProvider><TestConsumer /></I18nProvider>);
    expect(screen.getByTestId('languages')).toHaveTextContent('en,es');
  });

  it('falls back to key for unknown translation', () => {
    function Consumer() {
      const { t } = useI18n();
      return <span data-testid="unknown">{t('nonexistent.key')}</span>;
    }
    render(<I18nProvider><Consumer /></I18nProvider>);
    expect(screen.getByTestId('unknown')).toHaveTextContent('nonexistent.key');
  });
});
