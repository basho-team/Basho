// Webpack precisa do plugin PostCSS; Turbopack mantém seu loader nativo existente.
const config = {
  plugins: process.env.BASHO_WEBPACK_BUILD === "1" ? { "@tailwindcss/postcss": {} } : {},
};

export default config;
