import ProjectModule from "@/components/modules/ProjectModule";
import { createInitialState } from "@/data/seedData";
export function generateStaticParams() {
  return createInitialState().projects.map((p) => ({ id: p.id }));
}
export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ProjectModule projectId={id} />;
}
