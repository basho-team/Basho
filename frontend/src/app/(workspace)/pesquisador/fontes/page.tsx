import { redirect } from "next/navigation";

/** As fontes são conectadas pela organização; não há o que conectar por pessoa. */
export default function FontesPage() {
  redirect("/integracoes");
}
