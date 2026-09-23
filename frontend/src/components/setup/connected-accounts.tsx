"use client";

/*
 * Cadence's ConnectScreen / PlatformCard / OAuthPopup for the active client —
 * with real OAuth instead of the prototype's simulated popup. The permission
 * dialog lists the scopes this server actually requests, then hands off to the
 * provider's own consent page; nothing here pretends to be that page.
 *
 * Used by Setup › Accounts and by the Settings › Platforms tab.
 */

import Link from "next/link";
import { useCallback, useEffect, useState, type ComponentType } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  Facebook,
  Instagram,
  Link2,
  Linkedin,
  Loader2,
  Lock,
  MessageCircle,
  Music2,
  ShieldCheck,
  Sparkle,
  Twitter,
  Unplug,
  Youtube,
  AtSign,
  Cloud,
} from "lucide-react";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { ConfirmDialog, ErrorBanner } from "@/components/ui/feedback";
import { Eyebrow, Panel } from "@/components/ui/panel";
import { PostDialog } from "@/components/posts/dialog";
import { clientLabel, useActiveClient } from "@/lib/active-client";
import { publishUnavailableReason } from "@/lib/platforms";
import { trackFeature } from "@/lib/analytics";
import { setupApi, createPkce, type ClientAccount, type ClientAccountsResponse } from "@/lib/api-setup";
import { cn } from "@/lib/utils";

type Icon = ComponentType<{ className?: string }>;

interface PlatformMeta {
  id: string;
  name: string;
  domain: string;
  icon: Icon;
  /** Why it cannot be connected here; absent for the three real OAuth platforms. */
  unavailable?: string;
}

/** The three with real OAuth + publishing first, then Cadence's other platforms, honestly marked. */
const PLATFORMS: PlatformMeta[] = [
  { id: "twitter", name: "X (Twitter)", domain: "x.com", icon: Twitter },
  { id: "linkedin", name: "LinkedIn", domain: "linkedin.com", icon: Linkedin },
  { id: "facebook", name: "Facebook", domain: "facebook.com", icon: Facebook },
  {
    id: "instagram",
    name: "Instagram",
    domain: "instagram.com",
    icon: Instagram,
    unavailable: publishUnavailableReason("instagram") ?? "Instagram connection is not available yet.",
  },
  {
    id: "reddit",
    name: "Reddit",
    domain: "reddit.com",
    icon: MessageCircle,
    unavailable: "There is no Reddit connection or publisher yet. Posts can be drafted and published manually.",
  },
  {
    id: "threads",
    name: "Threads",
    domain: "threads.net",
    icon: AtSign,
    unavailable: "There is no Threads connection or publisher yet. Posts can be drafted and published manually.",
  },
  {
    id: "bluesky",
    name: "Bluesky",
    domain: "bsky.app",
    icon: Cloud,
    unavailable: "There is no Bluesky connection or publisher yet. Posts can be drafted and published manually.",
  },
  {
    id: "youtube",
    name: "YouTube",
    domain: "youtube.com",
    icon: Youtube,
    unavailable: "There is no YouTube connection yet. Video scripts can be written, but nothing uploads.",
  },
  {
    id: "tiktok",
    name: "TikTok",
    domain: "tiktok.com",
    icon: Music2,
    unavailable: publishUnavailableReason("tiktok") ?? "TikTok connection is not available yet.",
  },
];

/** Plain-language meaning of each scope the backend requests (routers/oauth.py::OAUTH_CONFIGS). */
const SCOPE_LABELS: Record<string, string> = {
  "tweet.read": "Read posts on the account",
  "tweet.write": "Publish posts you approve",
  "users.read": "Read the account's basic profile",
  "offline.access": "Stay connected without signing in again",
  openid: "Confirm who is signing in",
  profile: "Read your basic profile (name, photo)",
  w_member_social: "Publish posts you approve",
  pages_manage_posts: "Publish posts you approve to Pages you manage",
  pages_read_engagement: "Read Page content and engagement",
};

export function platformName(id: string): string {
  return PLATFORMS.find((p) => p.id === id)?.name ?? id;
}

export function ConnectedAccounts({ showContinue = true }: { showContinue?: boolean }) {
  const { active, activeId, refresh } = useActiveClient();
  const [data, setData] = useState<ClientAccountsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [consentFor, setConsentFor] = useState<PlatformMeta | null>(null);
  const [redirecting, setRedirecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState<ClientAccount | null>(null);
  const [disconnectBusy, setDisconnectBusy] = useState(false);

  const load = useCallback(async () => {
    if (!activeId) return;
    setLoading(true);
    setLoadError(false);
    try {
      setData(await setupApi.listAccounts(activeId));
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [activeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const byPlatform = (id: string) => (data?.accounts ?? []).filter((a) => a.platform === id);
  const connectable = PLATFORMS.filter((p) => !p.unavailable);
  const connectedCount = connectable.filter((p) => byPlatform(p.id).length > 0).length;

  const beginConnect = async () => {
    if (!consentFor || !activeId) return;
    setRedirecting(true);
    setConnectError(null);
    try {
      const challenge = consentFor.id === "twitter" ? await createPkce(consentFor.id) : undefined;
      const { authorize_url } = await setupApi.authorizeUrl(consentFor.id, activeId, challenge);
      // Same tab: the PKCE verifier lives in this tab's sessionStorage, and the
      // provider sends the user back to /api/oauth/<platform>/callback here.
      window.location.assign(authorize_url);
    } catch (e) {
      setConnectError(e instanceof Error ? e.message : "Could not start the connection.");
      setRedirecting(false);
    }
  };

  const confirmDisconnect = async () => {
    if (!disconnecting) return;
    setDisconnectBusy(true);
    try {
      await setupApi.disconnect(disconnecting.platform, disconnecting.id);
      toast.success(`Disconnected ${platformName(disconnecting.platform)}`);
      setDisconnecting(null);
      await Promise.all([load(), refresh()]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not disconnect");
    } finally {
      setDisconnectBusy(false);
    }
  };

  if (!active) return null;

  return (
    <Panel dashed className="p-6 motion-safe:animate-screen-in sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Eyebrow>Wire up {clientLabel(active)}&apos;s channels</Eyebrow>
          <h2 className="mt-3 font-display text-[23px] leading-snug text-ink">
            Connect where their audience already is.
            <br />
            <span className="text-[15px] text-muted">You can add more later — start with one.</span>
          </h2>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-mono text-[26px] leading-none text-accent-text">
            {loading && !data ? "–" : connectedCount}
            <span className="text-base text-muted">/{connectable.length}</span>
          </div>
          <div className="mt-0.5 text-[10.5px] text-muted">live</div>
        </div>
      </div>

      {/* Proactive trust strip — both real anxieties addressed before anyone connects anything. */}
      <div className="mt-6 flex flex-col gap-4 rounded-lg border border-line bg-canvas/50 p-4 sm:flex-row">
        <div className="flex flex-1 items-start gap-2.5 text-[11.5px] leading-relaxed text-slate-600">
          <ShieldCheck className="mt-px h-3.5 w-3.5 shrink-0 text-accent-text" />
          These are real connections: X, LinkedIn and Facebook publish to the live account. Nothing is posted until you
          approve it, and you sign in on the platform&apos;s own page — we never see the password.
        </div>
        <div className="flex flex-1 items-start gap-2.5 text-[11.5px] leading-relaxed text-slate-600">
          <Sparkle className="mt-px h-3.5 w-3.5 shrink-0 text-accent-text" />
          Connecting is free and unlimited — it never counts against your monthly generations, no matter how many
          channels you add.
        </div>
      </div>

      {loadError ? (
        <ErrorBanner message="Couldn't load connected accounts." onRetry={() => void load()} />
      ) : (
        <div className="mt-5 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {PLATFORMS.map((p, i) => (
            <PlatformCard
              key={p.id}
              platform={p}
              accounts={byPlatform(p.id)}
              configured={data?.oauth[p.id]?.configured ?? false}
              loading={loading && !data}
              delay={i * 0.06}
              onConnect={() => {
                setConnectError(null);
                setConsentFor(p);
              }}
              onDisconnect={setDisconnecting}
            />
          ))}
        </div>
      )}

      {showContinue && (
        <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-line pt-5">
          {connectedCount > 0 ? (
            <Link href="/content" className={buttonVariants()}>
              Continue to posts <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          ) : (
            <Button disabled>
              Continue to posts <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          )}
          <span className="text-[11.5px] text-muted">
            {connectedCount === 0 ? "Connect at least one channel to continue" : "Nice — you're ready to post"}
          </span>
        </div>
      )}

      <PostDialog
        open={consentFor !== null}
        onOpenChange={(o) => !o && !redirecting && setConsentFor(null)}
        busy={redirecting}
        title={
          consentFor && (
            <span className="flex flex-col gap-3">
              <span className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-full border border-line text-ink">
                  <consentFor.icon className="h-4 w-4" />
                </span>
                <ArrowRight className="h-3.5 w-3.5 text-muted" />
                <span className="flex h-10 w-10 items-center justify-center border border-accent text-accent-text">
                  <Sparkle className="h-4 w-4" />
                </span>
              </span>
              <span>
                Connect {consentFor.name} for <span className="text-accent-text">{clientLabel(active)}</span>
              </span>
            </span>
          )
        }
        description={
          consentFor &&
          `You'll sign in on ${consentFor.domain} and approve access there. CampaignForge will ask for:`
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setConsentFor(null)} disabled={redirecting} className="sm:flex-1">
              Cancel
            </Button>
            <Button onClick={() => void beginConnect()} disabled={redirecting} className="sm:flex-1">
              {redirecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Lock className="h-3.5 w-3.5" />}
              {redirecting ? `Redirecting to ${consentFor?.domain}…` : `Continue to ${consentFor?.domain}`}
            </Button>
          </>
        }
      >
        {consentFor && (
          <div className="space-y-2">
            {(data?.oauth[consentFor.id]?.scopes ?? []).map((scope, i) => (
              <div
                key={scope}
                className="flex items-start gap-2 motion-safe:animate-screen-in"
                style={{ animationDelay: `${i * 0.05}s` }}
              >
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
                <span className="text-[12.5px] text-slate-600">
                  {SCOPE_LABELS[scope] ?? scope} <span className="font-mono text-[10.5px] text-muted">({scope})</span>
                </span>
              </div>
            ))}
            <div className="mt-4 flex items-center gap-2 rounded-md border border-line bg-sky-50/40 px-3 py-2">
              <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-muted" />
              <span className="font-mono text-[10.5px] text-muted">
                Posts publish only after you approve them. You can disconnect at any time.
              </span>
            </div>
            {connectError && <ErrorBanner message={connectError} onRetry={() => void beginConnect()} />}
          </div>
        )}
      </PostDialog>

      <ConfirmDialog
        open={disconnecting !== null}
        title={disconnecting ? `Disconnect ${platformName(disconnecting.platform)}?` : ""}
        message="Scheduled posts for this platform can't publish until you reconnect. Approved and draft posts are kept."
        confirmLabel="Disconnect"
        busy={disconnectBusy}
        onConfirm={() => void confirmDisconnect()}
        onCancel={() => setDisconnecting(null)}
      />
    </Panel>
  );
}

function PlatformCard({
  platform,
  accounts,
  configured,
  loading,
  delay,
  onConnect,
  onDisconnect,
}: {
  platform: PlatformMeta;
  accounts: ClientAccount[];
  configured: boolean;
  loading: boolean;
  delay: number;
  onConnect: () => void;
  onDisconnect: (account: ClientAccount) => void;
}) {
  const connected = accounts.length > 0;
  const Icon = platform.icon;
  const unavailable = Boolean(platform.unavailable);
  const notConfigured = !unavailable && !loading && !configured;

  return (
    <div
      style={{ animationDelay: `${delay}s` }}
      className={cn(
        "rounded-xl border p-4 transition-all duration-200 motion-safe:animate-screen-in",
        connected ? "border-emerald-300 bg-emerald-50/50" : unavailable ? "border-dashed border-line bg-panel/40" : "border-line bg-panel/70"
      )}
    >
      <div
        className={cn(
          "mb-3 flex h-8 w-8 items-center justify-center rounded-lg border",
          connected ? "border-emerald-500 text-emerald-600" : "border-slate-300 text-muted"
        )}
      >
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="mb-0.5 text-[13.5px] font-medium text-ink">{platform.name}</div>
      <div
        className={cn(
          "mb-3 flex items-center gap-1.5 text-[10.5px]",
          connected ? "text-emerald-700" : "text-muted"
        )}
      >
        <span
          aria-hidden
          className={cn(
            "h-1.5 w-1.5 shrink-0 rounded-full",
            connected ? "bg-emerald-500 shadow-[0_0_5px_rgb(16_185_129/0.8)]" : "bg-slate-400"
          )}
        />
        {loading ? "Checking…" : connected ? "Connected" : unavailable ? "Not available yet" : "Not connected"}
      </div>

      {unavailable ? (
        <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-muted">
          <Clock className="mt-0.5 h-3 w-3 shrink-0" />
          {platform.unavailable}
        </p>
      ) : connected ? (
        <div className="space-y-1.5">
          {accounts.map((a) => (
            <div key={a.id} className="flex items-center justify-between gap-2">
              <span className="truncate font-mono text-[11px] text-slate-600" title={a.display_name ?? undefined}>
                {a.account_handle || a.display_name || "Connected account"}
              </span>
              <button
                type="button"
                onClick={() => onDisconnect(a)}
                className="press-scale flex shrink-0 items-center gap-1 text-[11px] font-medium text-muted hover:text-ink"
              >
                <Unplug className="h-3 w-3" /> Disconnect
              </button>
            </div>
          ))}
        </div>
      ) : (
        <>
          <Button size="sm" className="w-full" disabled={loading || notConfigured} onClick={onConnect}>
            <Link2 className="h-3.5 w-3.5" /> Connect
          </Button>
          {notConfigured && (
            <p className="mt-2 text-[10.5px] leading-relaxed text-muted">
              {platform.name} sign-in isn&apos;t set up on this server yet — an admin needs to add its app credentials.
            </p>
          )}
        </>
      )}
    </div>
  );
}

/** Success/failure banner shown after the provider redirects back (see the OAuth callback page). */
export function useConnectedToast(platform: string | null) {
  useEffect(() => {
    if (!platform) return;
    toast.success(`${platformName(platform)} connected`);
    trackFeature("connect-account");
  }, [platform]);
}
