# Mockups: indicador de set actual + retirada del selector horizontal

> Documento de exploración. **No** se ha tocado código aún. El usuario revisa
> y elige una opción; la implementación va en una iteración posterior.

## Por qué este cambio

- El selector horizontal (`set-pagination`) servía para navegar a sets
  pasados y editarlos. Con el undo log centralizado en servidor
  (`POST /game/undo` → `pop_last_forward()` en `app/api/action_log.py`),
  cualquier corrección se hace deshaciendo, no editando un set anterior
  manualmente.
- Además `currentSet` se autocomputa siempre desde `team_1.sets +
  team_2.sets (+1 si no terminó)` en `frontend/src/App.tsx:140-146`,
  así que cualquier cambio manual se sobrescribe en el siguiente
  refresco. El selector ya no sirve para nada útil.
- Quitar la fila libera **~32–36 px verticales** (botón 28 px + paddings)
  que en móvil landscape comprimido el panel central agradece.

Queda el problema de **dónde** ubicar un nuevo indicador "set actual"
muy compacto (solo el número). En **portrait** el centro está vacío
entre los dos botones de sets, así que es trivial. En **landscape** el
centro ya lo ocupan logos + tabla histórica de scores, y no queremos
que esa tabla baje en vertical.

---

## Estado actual (referencia)

### Landscape

```
   ┌─────┐  ┌──┐  ┌──┐   ┌─────┐
   │     │  │L1│  │L2│   │     │
   │ T1  │  ├──┤  ├──┤   │ T2  │   ← .sets-row (48 px)
   │sets │  │25│  │23│   │sets │
   │ 48  │  │25│  │27│   │ 48  │
   │ px  │  │23│  │25│   │ px  │
   └─────┘  └──┘  └──┘   └─────┘
                ↑          ↑
            tablas         botones
            histórico      grandes
            (interior)     (set count)

         ◀  ① ② ③ ④ ⑤  ▶          ← .set-pagination (~32 px) ❌ a quitar

         [   match-alerts-row   ]
```

### Portrait

```
   ┌─────┐                   ┌─────┐
   │ T1  │                   │ T2  │
   │sets │     (vacío)       │sets │
   └─────┘                   └─────┘

         ◀  ① ② ③ ④ ⑤  ▶          ← ❌ a quitar

         [   match-alerts-row   ]
```

---

## Opción A — Indicador entre las columnas del histórico

El número va en una **tercera columna central** dentro de
`logos-scores-section`, flanqueado por las dos `ScoreTable` actuales.

### Landscape

```
   ┌─────┐  ┌──┐ ┌───┐ ┌──┐   ┌─────┐
   │     │  │L1│ │   │ │L2│   │     │
   │ T1  │  ├──┤ │ 3 │ ├──┤   │ T2  │
   │sets │  │25│ │   │ │23│   │sets │
   │     │  │25│ │   │ │27│   │     │
   │     │  │23│ │   │ │25│   │     │
   └─────┘  └──┘ └───┘ └──┘   └─────┘
                  ↑
           indicador (~24 px de
           ancho, alto = columna)

         [   match-alerts-row   ]   ← gana ~32 px verticales
```

### Portrait

```
   ┌─────┐         ┌───┐         ┌─────┐
   │ T1  │         │ 3 │         │ T2  │
   │sets │         │   │         │sets │
   └─────┘         └───┘         └─────┘
```

> En portrait, como hoy `logos-scores-section` no se renderiza
> (`!isPortrait`), el número se coloca directamente dentro de
> `sets-row` como un nuevo hijo central.

### Cambios

- `CenterPanel.tsx`: añadir `<div className="current-set-indicator">{currentSet}</div>`
  - en landscape, dentro de `logos-scores-section` entre las dos `team-score-column`
  - en portrait, como hijo directo de `sets-row` entre los dos `ScoreButton`
- `App.css`: nueva regla `.current-set-indicator` (font-size grande pero
  con line-height: 1, color `var(--text-muted)` o `#009688` para reusar
  el verde del active actual del selector).

### Pros / Contras

- ✓ Cero impacto en altura: el indicador comparte la altura de la
  columna histórica.
- ✓ Sigue la sugerencia explícita del usuario.
- ✓ Cambio mínimo de DOM, fácil de testear.
- ✗ En landscape el número queda "encerrado" entre dos columnas de
  números — puede leerse como una columna histórica más si no se
  estiliza distinto.

---

## Opción B — Tablas históricas al exterior, número grande en el centro

Las dos `ScoreTable` se mueven al **exterior** de los marcadores de
sets (T1 a la izquierda del botón de sets de T1, T2 a la derecha del
botón de sets de T2). El centro entre los dos botones queda libre y
hospeda un número grande con los logos encima.

### Landscape

```
   ┌──┐  ┌─────┐                        ┌─────┐  ┌──┐
   │25│  │     │   ┌──┐    ┌──┐         │     │  │23│
   │25│  │ T1  │   │L1│    │L2│         │ T2  │  │27│
   │23│  │sets │   └──┘    └──┘         │sets │  │25│
   │  │  │     │     ┌──────┐           │     │  │  │
   │  │  │     │     │  3   │           │     │  │  │
   │  │  │     │     │ ~32px│           │     │  │  │
   └──┘  └─────┘     └──────┘           └─────┘  └──┘
    ↑       ↑           ↑                  ↑       ↑
  tabla   botón     número grande        botón   tabla
  T1      T1 sets   con logos arriba     T2      T2 sets
```

### Portrait

```
   ┌─────┐         ┌───┐         ┌─────┐
   │ T1  │         │ 3 │         │ T2  │
   │sets │         │   │         │sets │
   └─────┘         └───┘         └─────┘
```

### Cambios

- `CenterPanel.tsx`: reordenar `sets-row` a 5 hijos:
  `[ScoreTable T1] [SetButton T1] [center: logos+number] [SetButton T2] [ScoreTable T2]`.
  Las `ScoreTable` salen de `logos-scores-section` y `logos-scores-section`
  se simplifica a `[logos] + number`.
- `App.css`: `.sets-row` con `align-items: center` para que el número
  grande quede centrado verticalmente respecto a los botones; ajustar
  gaps a la baja para no ensanchar demasiado.

### Pros / Contras

- ✓ Indicador muy visible (número grande central).
- ✓ Sigue la otra sugerencia explícita del usuario.
- ✓ Recupera mucho ancho útil para el número.
- ✗ Reorganización fuerte del layout. Riesgo de regresiones en mobile
  estrecho: 2 columnas + 3 botones + 2 logos en una sola fila puede
  desbordar en pantallas pequeñas.
- ✗ Cambia mucho la estética actual; no es un cambio "mínimo".
- ✗ En portrait, los logos ya no se muestran (no es nuevo, pero la
  asimetría con landscape se acentúa).

---

## Opción C — Número en cabecera, sustituyendo el espacio del logo

El número se coloca **encima de las tablas** en una columna central
nueva, ocupando la misma altura que la fila de logos (24 px). Los
logos se mantienen sobre cada tabla; el número va en columna propia
sin logo. Altura total = altura actual.

### Landscape

```
   ┌─────┐  ┌──┐ ┌───┐ ┌──┐   ┌─────┐
   │     │  │L1│ │ 3 │ │L2│   │     │   ← fila de "cabecera" (24 px)
   │ T1  │  ├──┤ ╞═══╡ ├──┤   │ T2  │
   │sets │  │25│       │23│   │sets │
   │     │  │25│       │27│   │     │
   │     │  │23│       │25│   │     │
   └─────┘  └──┘       └──┘   └─────┘
                  ↑
       número solo en cabecera,
       sin tabla debajo (queda
       hueco visualmente, o se
       puede llevar el "3" más
       abajo en su columna)
```

### Portrait

```
   ┌─────┐         ┌───┐         ┌─────┐
   │ T1  │         │ 3 │         │ T2  │
   │sets │         │   │         │sets │
   └─────┘         └───┘         └─────┘
```

### Cambios

- `CenterPanel.tsx`: añadir `team-score-column` central con sólo el
  número en lugar de logo, sin `ScoreTable`.
- `App.css`: el centro hereda `min-height: 130px` de `team-score-column`,
  así que el número puede centrarse vertical o quedarse alineado a la
  cabecera.

### Pros / Contras

- ✓ Reusa la rejilla existente (3 `team-score-column` en lugar de 2),
  cambio quirúrgico.
- ✓ Misma altura total — no toca `min-height: 130px`.
- ✓ El número queda alineado con los logos, lectura natural.
- ✗ Si se centra el número verticalmente, queda "flotando" y vacío
  arriba/abajo. Si se sube a la cabecera, queda demasiado pequeño
  comparado con el espacio total.

---

## Opción D — Indicador como badge absoluto sobre `sets-row`

El número se renderiza con `position: absolute` sobre el centro de
`sets-row`, sin participar del flujo. La tabla histórica no se mueve.

### Landscape

```
   ┌─────┐  ┌──┐ ┌──┐   ┌─────┐
   │     │  │L1│ │L2│   │     │
   │ T1  │  ├──┤ ├──┤   │ T2  │
   │sets │  │25│ │23│   │sets │      ⌐ ¬
   │     │  │25│ │27│   │     │      │3│  ← badge absoluto
   │     │  │23│ │25│   │     │      └ ┘    centrado en sets-row
   └─────┘  └──┘ └──┘   └─────┘
```

(en realidad el badge va por encima del centro de la fila, no a la
derecha — no hay forma elegante de dibujarlo en ASCII)

### Portrait

```
   ┌─────┐                         ┌─────┐
   │ T1  │           ┌───┐         │ T2  │
   │sets │           │ 3 │         │sets │
   └─────┘           └───┘         └─────┘
                  (centrado por
                   absoluto)
```

### Cambios

- `CenterPanel.tsx`: añadir un `<div className="current-set-indicator
  current-set-indicator-overlay">{currentSet}</div>` como hijo de
  `sets-row` (o de `center-panel`).
- `App.css`: `.sets-row { position: relative; }` y
  `.current-set-indicator-overlay { position: absolute; left: 50%;
  top: 50%; transform: translate(-50%, -50%); pointer-events: none; }`.

### Pros / Contras

- ✓ Cero cambio estructural — el resto del panel queda intacto.
- ✓ El número puede ser tan grande como queramos sin afectar layout.
- ✗ Riesgo de solapamiento visual con la tabla histórica si se
  agranda. En landscape es probable que pise números.
- ✗ No es accesible al tab/teclado (no problemático: el indicador es
  pasivo, pero conviene `aria-hidden="true"`).

---

## Recomendación

**Opción A (entre columnas del histórico)** como primera elección:

- Riesgo más bajo (cambio quirúrgico de DOM y CSS).
- Mantiene la altura total exacta.
- Coincide con la primera sugerencia explícita del usuario.
- Fácil de revertir si no convence visualmente.

**Opción B** como segunda elección si lo importante es que el número
sea muy visible (números grandes para visualización a distancia).

**Opciones C y D** quedan como respaldo: C por si la rejilla de 3
columnas resulta más limpia que insertar una intermedia; D si
preferimos cero cambios estructurales y aceptamos un overlay.

---

## Cambios comunes a cualquier opción

Independientes de la maquetación elegida:

- **Borrar selector horizontal** en `frontend/src/components/CenterPanel.tsx`
  (líneas 124–148, bloque `set-pagination`).
- **Borrar CSS del selector** en `frontend/src/App.css` (líneas
  578–626: `.set-pagination`, `.pagination-arrow`, `.pagination-page`,
  `.pagination-page-active`).
- **Quitar prop `onSetChange`** de:
  - `CenterPanelProps` (`CenterPanel.tsx:38`)
  - `ScoreboardViewProps` (`ScoreboardView.tsx:52`)
  - llamada en `App.tsx:409`
- **Borrar `handleSetChange`** en `App.tsx:257-263`.
- **Mantener** `currentSet` y su `useEffect` autocomputado en
  `App.tsx:148-154` — sigue siendo consumido por `ScoreTable`,
  `TeamPanel`, `useIndoorMidpointAlert` y el diálogo de edición de
  score (`App.tsx:323`).
- **Tests** en `frontend/src/test/CenterPanel.test.tsx`:
  - Eliminar los 6 tests de paginación (líneas 49–104).
  - Quitar `onSetChange` de `defaultProps` (línea 16).
  - Añadir test del nuevo indicador
    (`getByTestId('current-set-indicator')` con el número correcto,
    en portrait y landscape).

---

## Próximos pasos

1. Revisar este documento.
2. Elegir A / B / C / D (o pedir variaciones).
3. Implementación en commit posterior:
   - aplicar cambios comunes,
   - aplicar cambios específicos de la opción elegida,
   - actualizar tests,
   - validar visualmente en navegador (portrait + landscape comprimido).
