import { Suspense } from "react";
import { Chat } from "@/components/chat";

export default function Home() {
  return (
    <Suspense>
      <Chat />
    </Suspense>
  );
}
