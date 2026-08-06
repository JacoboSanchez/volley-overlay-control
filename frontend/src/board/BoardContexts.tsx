import { createContext, useContext, type ReactNode } from 'react';
import type { SetSummaryStyle, GameState } from '../api/board';
import type { ConfigModel } from '../components/TeamCard';
import type { PreviewData } from '../components/CenterPanel';
import type { ScoreButtonFontStyle } from '../components/ScoreButton';
import type { RecentEvent } from '../hooks/useRecentEvents';

type Team = 1 | 2;

/** Live and derived board data shared by the score-facing components. */
export interface BoardStateValue {
  state: GameState;
  confirmedState: GameState | null;
  customization: ConfigModel | null | undefined;
  currentSet: number;
  setsLimit: number;
  simpleMode: boolean;
  matchFinished: boolean;
  sidesSwapped: boolean;
  previewData: PreviewData | null | undefined;
  showPreview: boolean;
  setSummaryEnabled: boolean;
  showOnAir: boolean;
  showReportLink: boolean;
  recentEvents: RecentEvent[];
}

/** Operator callbacks. Their provider value is memoized by App. */
export interface BoardActionsValue {
  onAddPoint: (team: Team) => void;
  onAddSet: (team: Team) => void;
  onAddTimeout: (team: Team) => void;
  onChangeServe: (team: Team) => void;
  onDoubleTapScore: (team: Team) => void;
  onDoubleTapTimeout: (team: Team) => void;
  onLongPressScore: (team: Team) => void;
  onLongPressSet: (team: Team) => void;
  onSwapSides: () => void;
  onToggleVisibility: () => void;
  onToggleSimpleMode: () => void;
  onUndoLast: () => void;
  onTogglePreview: () => void;
  onToggleSetSummary: () => void;
  onChangeSetSummaryStyle: (style: SetSummaryStyle) => void;
  onStartMatch: () => void;
  onReset: () => void;
  onOpenConfig: () => void;
  onOpenShare: () => void;
  onOpenHistory: () => void;
  onToggleControls: () => void;
}

/** Score-button colors, logos and typography resolved from user settings. */
export interface BoardThemeValue {
  btnColorA: string;
  btnTextA: string;
  btnColorB: string;
  btnTextB: string;
  iconLogoA: string | null;
  iconLogoB: string | null;
  iconOpacity?: number;
  fontStyle: ScoreButtonFontStyle;
}

/** Viewport-derived board layout values. */
export interface BoardLayoutValue {
  isPortrait: boolean;
  buttonSize?: number;
  compactLandscape: boolean;
  showControls: boolean;
}

const BoardStateContext = createContext<BoardStateValue | null>(null);
const BoardActionsContext = createContext<BoardActionsValue | null>(null);
const BoardThemeContext = createContext<BoardThemeValue | null>(null);
const BoardLayoutContext = createContext<BoardLayoutValue | null>(null);

export interface BoardContextProviderProps {
  state: BoardStateValue;
  actions: BoardActionsValue;
  theme: BoardThemeValue;
  layout: BoardLayoutValue;
  children: ReactNode;
}

/**
 * Groups the deliberately split board contexts at the App boundary. Keeping
 * live match data separate from stable handlers, theme, and layout means a
 * state push only notifies consumers of the data they actually read.
 */
export function BoardContextProvider({
  state,
  actions,
  theme,
  layout,
  children,
}: BoardContextProviderProps) {
  return (
    <BoardStateContext.Provider value={state}>
      <BoardActionsContext.Provider value={actions}>
        <BoardThemeContext.Provider value={theme}>
          <BoardLayoutContext.Provider value={layout}>{children}</BoardLayoutContext.Provider>
        </BoardThemeContext.Provider>
      </BoardActionsContext.Provider>
    </BoardStateContext.Provider>
  );
}

function missingProvider(name: string): never {
  throw new Error(`${name} must be used within a BoardContextProvider`);
}

export function useBoardState(): BoardStateValue {
  return useContext(BoardStateContext) ?? missingProvider('useBoardState');
}

export function useBoardActions(): BoardActionsValue {
  return useContext(BoardActionsContext) ?? missingProvider('useBoardActions');
}

export function useBoardTheme(): BoardThemeValue {
  return useContext(BoardThemeContext) ?? missingProvider('useBoardTheme');
}

export function useBoardLayout(): BoardLayoutValue {
  return useContext(BoardLayoutContext) ?? missingProvider('useBoardLayout');
}
