"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import {
  AMPLIFY_MAX_ATOMS,
  amplifyApi,
  api,
  apiErrorStatus,
  isGenerationQuotaError,
  unusableReason,
  type AmplifyPack,
  type AmplifyPreviewResponse,
  type Client,
  type ContentPiece,
  type SubscriptionInfo,
} from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { useActiveClient } from "@/lib/active-client";
import { foundationApi } from "@/lib/api-foundation";
import { REPURPOSABLE_KINDS, collectRepurposeSources, type RepurposeSource } from "@/lib/api-create-content";
import { PageHeader } from "@/components/ui/panel";
import { AmplifyForm, type SourceMode } from "@/components/amplify/amplify-form";
import { AtomReview } from "@/components/amplify/atom-review";
import { PackHistory } from "@/components/amplify/pack-history";

const DEFAULT_PLATFORMS = ["twitter", "linkedin"];

function errorMessage(err: unknown, fallback: string): string {
  const status = apiErrorStatus(err);
  if (status === 404) return "That client or source no longer exists in this workspace.";
  if (status === 422) return "Something in the request was rejected. Check the source and platforms, then try again.";
  if (err instanceof Error && err.message && err.message !== "[object Object]") return err.message;
  return fallback;
}

function AmplifyWorkspace() {
  const router = useRouter();
  const { activeId } = useActiveClient();
  const params = useSearchParams();
  const sourceParam = params.get("source");

  const [clients, setClients] = useState<Client[]>([]);
  const [clientsLoading, setClientsLoading] = useState(true);
  const [clientId, setClientId] = useState("");
  const [sourceMode, setSourceMode] = useState<SourceMode>("content");
  const [contentItems, setContentItems] = useState<ContentPiece[]>([]);
  const [contentLoading, setContentLoading] = useState(false);
  const [sourceId, setSourceId] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [assetSources, setAssetSources] = useState<RepurposeSource[]>([]);
  const [assetLoading, setAssetLoading] = useState(false);
  const [sourceAssetId, setSourceAssetId] = useState("");
  const [platforms, setPlatforms] = useState<string[]>(DEFAULT_PLATFORMS);
  const [maxAtoms, setMaxAtoms] = useState<number>(AMPLIFY_MAX_ATOMS);

  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [quotaBlocked, setQuotaBlocked] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const [pack, setPack] = useState<AmplifyPreviewResponse | null>(null);
  const [dropped, setDropped] = useState<Set<number>>(new Set());
  const [committing, setCommitting] = useState(false);
  const [committedCount, setCommittedCount] = useState<number | null>(null);

  const [packs, setPacks] = useState<AmplifyPack[]>([]);
  const [packsLoading, setPacksLoading] = useState(true);

  const loadSubscription = useCallback(() => {
    api
      .getSubscription()
      .then(setSubscription)
      .catch(() => setSubscription(null)); // unknown quota renders nothing, never a guess
  }, []);

  const loadPacks = useCallback(() => {
    amplifyApi
      .packs()
      .then((r) => setPacks(r.items))
      .catch(() => setPacks([]))
      .finally(() => setPacksLoading(false));
  }, []);

  useEffect(() => {
    api
      .getClients()
      .then((r) => setClients(r.items))
      .catch(() => toast.error("Could not load clients"))
      .finally(() => setClientsLoading(false));
    loadSubscription();
    loadPacks();
    return () => controllerRef.current?.abort();
  }, [loadSubscription, loadPacks]);

  // CF-10: start on the client the top-nav switcher is pointing at, rather than
  // an empty picker. Seeds the empty field only, so a deep link's client (set
  // below) and any deliberate pick both survive.
  useEffect(() => {
    if (activeId) setClientId((current) => current || activeId);
  }, [activeId]);

  // Deep link from the queue / campaign cards: /amplify?source=<content_id>.
  useEffect(() => {
    if (!sourceParam) return;
    api
      .getContentPiece(sourceParam)
      .then((piece) => {
        // A deep link can point at a piece that has nothing in it — say, an ad
        // variant the agent returned empty. Amplifying it would spend a
        // generation on nothing (CF-05).
        const unusable = unusableReason(piece);
        if (piece.status === "failed" || unusable !== null) {
          toast.error(unusable ?? "That post failed, so there's nothing to amplify.");
          return;
        }
        setSourceMode("content");
        setClientId(piece.client_id);
        setSourceId(piece.id);
        setContentItems((items) => (items.some((i) => i.id === piece.id) ? items : [piece, ...items]));
      })
      .catch(() => toast.error("That content piece could not be found"));
  }, [sourceParam]);

  useEffect(() => {
    if (!clientId) {
      setContentItems([]);
      return;
    }
    let cancelled = false;
    setContentLoading(true);
    api
      .getContent({ client_id: clientId, per_page: 50 })
      .then((r) => {
        if (cancelled) return;
        // CF-05: a failed or empty piece must not be offered as a source. There
        // is nothing in it to repurpose, so a pack built from one would spend a
        // generation to produce eight drafts of nothing.
        const usable = r.items.filter((i) => i.status !== "failed" && unusableReason(i) === null);
        setContentItems((prev) => {
          // Keep a deep-linked piece that is older than the first page.
          const pinned = prev.filter((p) => p.id === sourceId && p.client_id === clientId && !usable.some((i) => i.id === p.id));
          return [...pinned, ...usable];
        });
      })
      .catch(() => !cancelled && setContentItems([]))
      .finally(() => !cancelled && setContentLoading(false));
    return () => {
      cancelled = true;
    };
    // sourceId is read only to preserve a pinned deep-link; refetching on every
    // source change would be wasteful.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  // Saved Create-screen output for this client — Cadence's collectRepurposeSources.
  useEffect(() => {
    setSourceAssetId("");
    if (!clientId) {
      setAssetSources([]);
      return;
    }
    let cancelled = false;
    setAssetLoading(true);
    foundationApi
      .listAssets({ clientId, kinds: REPURPOSABLE_KINDS, limit: 100 })
      .then((r) => !cancelled && setAssetSources(collectRepurposeSources(r.items)))
      .catch(() => !cancelled && setAssetSources([]))
      .finally(() => !cancelled && setAssetLoading(false));
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  const generationsUsed = subscription?.generations_used ?? null;
  const generationsLimit = subscription?.generations_limit ?? null;
  const quotaExhausted =
    quotaBlocked || (generationsUsed != null && generationsLimit != null && generationsUsed >= generationsLimit);

  function resetPack() {
    setPack(null);
    setDropped(new Set());
    setCommittedCount(null);
  }

  async function handleGenerate() {
    setError(null);
    resetPack();
    const controller = new AbortController();
    controllerRef.current = controller;
    setGenerating(true);
    try {
      const result = await amplifyApi.preview(
        {
          client_id: clientId,
          ...(sourceMode === "content"
            ? { source_content_id: sourceId }
            : sourceMode === "asset"
              ? { source_asset_id: sourceAssetId }
              : { source_text: sourceText.trim() }),
          platforms,
          max_atoms: maxAtoms,
        },
        controller.signal
      );
      setPack(result);
      loadPacks();
    } catch (err) {
      if (controller.signal.aborted) {
        toast("Generation cancelled");
      } else if (isGenerationQuotaError(err)) {
        setQuotaBlocked(true);
      } else {
        setError(errorMessage(err, "Generation failed. No quota was used; try again."));
      }
    } finally {
      controllerRef.current = null;
      setGenerating(false);
      loadSubscription();
    }
  }

  function handleCancel() {
    controllerRef.current?.abort();
  }

  function toggleDrop(i: number) {
    setDropped((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  async function handleCommit() {
    if (!pack) return;
    const kept = pack.atoms
      .filter((_, i) => !dropped.has(i))
      .map(({ platform, angle, title, body, hashtags }) => ({ platform, angle, title, body, hashtags }));
    setCommitting(true);
    try {
      const res = await amplifyApi.commit(pack.pack_id, kept);
      setCommittedCount(res.count);
      trackFeature("amplify", { drafts: res.count });
      toast.success(`${res.count} ${res.count === 1 ? "draft" : "drafts"} added to the queue as Pending`, {
        action: { label: "Open queue", onClick: () => router.push("/content") },
      });
      loadPacks();
    } catch (err) {
      toast.error(
        apiErrorStatus(err) === 409 ? "This pack is already in the queue" : errorMessage(err, "Could not add drafts to the queue")
      );
    } finally {
      setCommitting(false);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Create"
        title="Amplify"
        description="Turn one piece of content into up to eight drafts, each a different angle, ready for review in the queue."
      />

      <AmplifyForm
        clients={clients}
        clientsLoading={clientsLoading}
        clientId={clientId}
        onClientChange={(id) => {
          setClientId(id);
          setSourceId("");
        }}
        sourceMode={sourceMode}
        onSourceModeChange={setSourceMode}
        contentItems={contentItems}
        contentLoading={contentLoading}
        sourceId={sourceId}
        onSourceChange={setSourceId}
        assetSources={assetSources}
        assetLoading={assetLoading}
        sourceAssetId={sourceAssetId}
        onSourceAssetChange={setSourceAssetId}
        sourceText={sourceText}
        onSourceTextChange={setSourceText}
        platforms={platforms}
        onTogglePlatform={(id) =>
          setPlatforms((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]))
        }
        maxAtoms={maxAtoms}
        onMaxAtomsChange={setMaxAtoms}
        generating={generating}
        onGenerate={handleGenerate}
        onCancel={handleCancel}
        generationsUsed={generationsUsed}
        generationsLimit={generationsLimit}
        quotaExhausted={quotaExhausted}
        error={error}
        locked={Boolean(pack) && committedCount === null}
      />

      {pack && (
        <AtomReview
          atoms={pack.atoms}
          requested={pack.requested}
          discarded={pack.dropped}
          dropped={dropped}
          onToggle={toggleDrop}
          onCommit={handleCommit}
          onDiscard={resetPack}
          committing={committing}
          committedCount={committedCount}
        />
      )}

      <PackHistory packs={packs} loading={packsLoading} />
    </div>
  );
}

export default function AmplifyPage() {
  // useSearchParams (the ?source= deep link) must sit under Suspense or the
  // route bails out of static rendering at build time.
  return (
    <Suspense fallback={null}>
      <AmplifyWorkspace />
    </Suspense>
  );
}
