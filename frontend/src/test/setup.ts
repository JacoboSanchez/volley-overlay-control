import '@testing-library/jest-dom/vitest';
import { beforeEach, vi } from 'vitest';

const store: Record<string, string> = {};
const localStorageMock = {
  getItem: vi.fn((key: string) => store[key] ?? null),
  setItem: vi.fn((key: string, value: string) => { store[key] = String(value); }),
  removeItem: vi.fn((key: string) => { delete store[key]; }),
  clear: vi.fn(() => {
    for (const key in store) {
      delete store[key];
    }
  }),
  get length() { return Object.keys(store).length; },
  key: vi.fn((i: number) => Object.keys(store)[i] ?? null),
};
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

beforeEach(() => {
  localStorage.clear();
  localStorageMock.getItem.mockClear();
  localStorageMock.setItem.mockClear();
  localStorageMock.removeItem.mockClear();
  localStorageMock.clear.mockClear();
});

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

document.documentElement.requestFullscreen = vi.fn().mockResolvedValue(undefined);
document.exitFullscreen = vi.fn().mockResolvedValue(undefined);
Object.defineProperty(document, 'fullscreenElement', { writable: true, value: null });
