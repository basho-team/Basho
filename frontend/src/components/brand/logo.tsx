import { cn } from "cn";

/**
 * Monograma Basho: um D vazado enlaçado a dois anéis. Aproximação desenhada em SVG a partir da
 * identidade visual; para usar o arquivo oficial, troque só o conteúdo de `BashoMark`.
 */
export function BashoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 40 40"
      fill="none"
      stroke="currentColor"
      strokeWidth={3.2}
      strokeLinejoin="round"
      strokeLinecap="round"
      aria-hidden
      className={cn("size-8 shrink-0", className)}
    >
      <path d="M5 5h10.5c7 0 11.5 4 11.5 10.5S22.5 26 15.5 26H5z" />
      <path d="M5 26v9h10.5c2.6 0 4.8-.7 6.5-2" />
      <circle cx="27" cy="13.5" r="7.5" />
      <circle cx="27" cy="27.5" r="7.5" />
    </svg>
  );
}

/** Marca + nome em serifa, como no logotipo. O texto acessível é o nome do produto. */
export function BashoLogo({ className, markClassName, nameClassName }: { className?: string; markClassName?: string; nameClassName?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <BashoMark className={markClassName} />
      <span className={cn("font-serif text-[1.65rem] leading-none font-semibold tracking-tight", nameClassName)}>basho</span>
    </span>
  );
}
