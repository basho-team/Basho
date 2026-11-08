import Link from "next/link";

export default function AccessDeniedPage() {
  return <section className="mx-auto max-w-lg space-y-4 rounded-2xl border bg-card p-8">
    <h1 className="text-2xl font-semibold">Esta área pertence a outra função</h1>
    <p className="text-muted-foreground">Seu acesso est? limitado ?s atividades da função autorizada para sua conta.</p>
    <Link href="/" className="inline-block rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">Voltar ao meu espaço</Link>
  </section>;
}
