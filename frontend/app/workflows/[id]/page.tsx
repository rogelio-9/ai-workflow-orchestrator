import { WorkflowDetail } from "@/components/WorkflowDetail";

// Server component: params is a promise in the App Router, and awaiting it
// here keeps the id out of the client bundle's routing logic. The data fetch
// still happens client-side -- see the note in the day 27 summary.
export default async function Page(props: PageProps<"/workflows/[id]">) {
  const { id } = await props.params;
  return <WorkflowDetail id={id} />;
}
