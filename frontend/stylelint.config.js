export default {
  // Recommended focuses on invalid/duplicated CSS rather than rewriting the
  // established overlay syntax. That matters for older OBS browser engines:
  // Stylelint's standard preset prefers modern color syntax that is not a
  // safe mechanical substitution for every deployed CEF version.
  extends: ['stylelint-config-recommended'],
  rules: {
    // Consecutive fallbacks such as `100vh` followed by `100dvh` keep older
    // OBS/CEF releases usable while newer engines get dynamic viewport units.
    'declaration-block-no-duplicate-properties': [
      true,
      { ignore: ['consecutive-duplicates-with-different-values'] },
    ],
    // Theme files intentionally place broad base selectors before their
    // variant overrides. The cascade is their API, not an ordering mistake.
    'no-descending-specificity': null,
  },
};
