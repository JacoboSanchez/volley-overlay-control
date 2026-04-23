import { useState, useEffect } from 'react';

export interface OrientationLayout {
  isPortrait: boolean;
  buttonSize: number;
}

function computeLayout(): OrientationLayout {
  const w = window.innerWidth;
  const h = window.innerHeight;
  const portrait = h > 1.2 * w && w <= 800;
  return {
    isPortrait: portrait,
    buttonSize: portrait ? Math.min(h / 4, 360) : Math.min(w / 3.5, 360),
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
