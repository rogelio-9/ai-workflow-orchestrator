import { RunTrace } from "@/components/RunTrace";

export default async function Page(props: PageProps<"/runs/[id]">) {
  const { id } = await props.params;
  return <RunTrace id={id} />;
}
