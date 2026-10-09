import WebCallLab from "@/components/WebCallLab";

export default async function WebCallLabPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <WebCallLab slug={slug} />;
}
