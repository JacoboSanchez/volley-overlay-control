import { useState, useEffect } from 'react';

export interface OrientationLayout {
  isPortrait: boolean;
  buttonSize: number;
  // True on tablets/desktops where the overlay control bar fits at the
  // bottom without covering scoreboard controls — used to skip auto-hide.
  hasRoomForPersistentControls: boolean;
}

// Material Design's tablet breakpoint: anything whose smaller side is at
// least 600 CSS px (e.g. iPad, desktop) has room to keep the bar pinned.
const PERSISTENT_CONTROLS_MIN_DIMENSION = 600;

function computeLayout(): OrientationLayout {
  const w = window.innerWidth;
  const h = window.innerHeight;
  const portrait = h > 1.2 * w && w <= 800;
  return {
    isPortrait: portrait,
    buttonSize: portrait ? Math.min(h / 4, 360) : Math.min(w / 3.5, 360),
    hasRoomForPersistentControls:
      Math.min(w, h) >= PERSISTENT_CONTROLS_MIN_DIMENSION,
  };
}

export function useOrientation(): OrientationLayout {
  const [layout, setLayout] = useState<OrientationLayout>(computeLayout);

  useEffect(() => {
    function handleResize() {
      setLayout(computeLayout());
    }
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return layout;
}
