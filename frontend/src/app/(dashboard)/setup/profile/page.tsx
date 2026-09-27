"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LoadingState } from "@/components/ui/empty-state";
import { ErrorBanner } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/panel";
import { BrandVoiceSection } from "@/components/setup/brand-voice-section";
import { CampaignSection } from "@/components/setup/campaign-section";
import { ActiveClientGate } from "@/components/setup/client-state";
import { Intake } from "@/components/setup/intake";
import { StrategyLensPanel } from "@/components/setup/strategy-lens-panel";
import { useGenerationQuota } from "@/components/setup/use-generation-quota";
import { clientLabel, useActiveClient } from "@/lib/active-client";
import { setupApi, type SetupProfile } from "@/lib/api-setup";

/**
 * Setup › Profile — Cadence's IntakeScreen for the active client, with the
 * Campaign, Brand Voice and Strategy Lens sections embedded after approval.
 */
export default function SetupProfilePage() {
  const { active } = useActiveClient();
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        eyebrow="Setup"
        title="Brand profile"
        description={
          active
            ? `Who ${clientLabel(active)} is for, what sets it apart and how it sounds — every generator reads this.`
            : "Who each client is for, what sets it apart and how it sounds."
        }
      />
      <ActiveClientGate>{active && <ProfileForClient key={active.id} clientId={active.id} />}</ActiveClientGate>
    </div>
  );
}

function ProfileForClient({ clientId }: { clientId: string }) {
  const router = useRouter();
  const { active, refresh } = useActiveClient();
  const quota = useGenerationQuota();
  const [profile, setProfile] = useState<SetupProfile | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setError(false);
    try {
      setProfile(await setupApi.getProfile(clientId));
    } catch {
      setError(true);
    }
  }, [clientId]);

  useEffect(() => {
    void load();
  }, [load]);

  // CampaignIndicator's "Edit" links to #campaign; the section only exists once loaded.
  useEffect(() => {
    if (profile && window.location.hash === "#campaign") {
      requestAnimationFrame(() => document.getElementById("campaign")?.scrollIntoView({ behavior: "smooth" }));
    }
  }, [profile]);

  if (error) return <ErrorBanner message="Couldn't load this client's brand profile." onRetry={() => void load()} />;
  if (!profile) return <LoadingState label="Loading the brand profile…" />;

  const name = clientLabel(active);

  return (
    <Intake
      clientId={clientId}
      clientName={name}
      profile={profile}
      onApproved={(saved, first) => {
        setProfile(saved);
        void refresh();
        // Cadence moves on to Connected accounts after the first approval.
        if (first && (active?.connected_accounts ?? 0) === 0) router.push("/setup/accounts");
      }}
    >
      <CampaignSection clientId={clientId} focus={profile.campaign_focus} />
      <BrandVoiceSection
        clientId={clientId}
        guide={profile.brand_voice}
        quota={quota}
        onSaved={(saved) => setProfile(saved)}
      />
      <StrategyLensPanel clientId={clientId} quota={quota} />
    </Intake>
  );
}
