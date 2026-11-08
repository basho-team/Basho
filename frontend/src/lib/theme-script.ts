/** Constantes e script do tema, sem hooks: o layout (Server Component) importa este módulo. */

export const THEME_STORAGE_KEY = "basho-theme";
export const DARK_QUERY = "(prefers-color-scheme: dark)";

/**
 * Roda no `<head>` antes da primeira pintura (guia "preventing flash before hydration" do Next).
 * Mesma regra de `resolveTheme`: `dark` salvo, ou sem preferência salva e SO escuro.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var s=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});var d=s==="dark"||(s!=="light"&&matchMedia(${JSON.stringify(
  DARK_QUERY,
)}).matches);var r=document.documentElement;r.classList.toggle("dark",d);r.style.colorScheme=d?"dark":"light"}catch(e){}})()`;
