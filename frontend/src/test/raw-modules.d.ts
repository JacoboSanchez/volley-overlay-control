// Vite's ``?raw`` suffix imports a file's contents as a string.
// Used by the overlay-script tests to load the plain non-module
// scripts under overlay_static/ into jsdom. (The project doesn't
// reference vite/client types, so declare the modules locally.)
declare module '*?raw' {
  const src: string;
  export default src;
}
