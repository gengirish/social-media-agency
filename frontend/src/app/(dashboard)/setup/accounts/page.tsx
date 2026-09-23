"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/ui/panel";
import { ActiveClientGate } from "@/components/setup/client-state";
import { ConnectedAccounts, useConnectedToast } from "@/components/setup/connected-accounts";
import { clientLabel, useActiveClient } from "@/lib/active-client";

function ConnectedToast() {
  useConnectedToast(useSearchParams().get("connected"));
  return null;
}

/** Setup › Accounts — Cadence's ConnectScreen, scoped to the active client. */
export default function SetupAccountsPage() {
  const { active } = useActiveClient();
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Suspense fallback={null}>
        <ConnectedToast />
      </Suspense>
      <PageHeader
        eyebrow="Setup"
        title="Connected accounts"
        description={
          active
            ? `Social accounts ${clientLabel(active)} publishes to. Each client connects its own.`
            : "Social accounts each client publishes to."
        }
      />
      <ActiveClientGate>
        <ConnectedAccounts />
      </ActiveClientGate>
    </div>
  );
}
