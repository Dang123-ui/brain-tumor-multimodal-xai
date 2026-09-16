import { NeuroBoardCaseDetail } from "@/components/neuroboard/NeuroBoardCaseDetail";

type Props = {
  params: Promise<{
    postId: string;
  }>;
};

export default async function NeuroBoardCaseDetailPage({ params }: Props) {
  const { postId } = await params;
  return <NeuroBoardCaseDetail postId={Number(postId)} />;
}
