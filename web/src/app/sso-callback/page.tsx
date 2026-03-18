"use client";

import { useClerk } from "@clerk/nextjs";
import { useEffect, useRef } from "react";

export default function SSOCallbackPage() {
  const clerk = useClerk();
  const hasRun = useRef(false);

  useEffect(() => {
    if (!clerk.loaded || hasRun.current) return;
    hasRun.current = true;

    clerk.handleRedirectCallback({
      signInForceRedirectUrl: "/",
      signUpForceRedirectUrl: "/",
    });
  }, [clerk.loaded]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-sm text-muted-foreground">Signing you in...</p>
    </div>
  );
}
