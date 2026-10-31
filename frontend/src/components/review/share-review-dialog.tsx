"use client";

/*
 * "Share for client review": makes a private link for one client (optionally one
 * campaign), shows it once, and lists the client's existing links so one can be
 * turned off.
 *
 * The server keeps only a hash of each link's token, so a link can be copied only
 * in the moment it is made. The copy says so rather than pretending a lost link can
 * be recovered: the answer is a new link and revoking the old one.
 */

import { useCallback, useEffect, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { Check, Copy, Link2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage, type ReviewLink } from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { PostDialog } from "@/components/posts/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";

function relative(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : formatDistanceToNow(d, { addSuffix: true });
}

export function ShareReviewDialog({
  open,
  onOpenChange,
  clientId,
  clientName,
  campaignId,
  campaignName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clientId: string;
  clientName: string;
  campaignId?: string;
  campaignName?: string;
}) {
  const [links, setLinks] = useState<ReviewLink[] | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .listReviewLinks(clientId)
      .then((res) => setLinks(res.items))
      .catch(() => setLinks([]));
  }, [clientId]);

  useEffect(() => {
    if (!open) return;
    setUrl(null);
    setCopied(false);
    setError(null);
    load();
  }, [open, load]);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const made = await api.createReviewLink(clientId, campaignId ? { campaign_id: campaignId } : {});
      setUrl(`${window.location.origin}${made.path}`);
      trackFeature("review-link-create", { scope: campaignId ? "campaign" : "client" });
      load();
    } catch (err) {
      setError(apiErrorMessage(err) ?? "Couldn't create a link. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      toast.error("Couldn't copy — select the link and copy it by hand.");
    }
  }

  async function revoke(link: ReviewLink) {
    try {
      await api.revokeReviewLink(link.id);
      toast.success("Link turned off — it no longer opens.");
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err) ?? "Couldn't turn that link off.");
    }
  }

  const active = (links ?? []).filter((l) => l.state === "active");
  const scope = campaignName ? `${campaignName} (${clientName})` : clientName;

  return (
    <PostDialog
      open={open}
      onOpenChange={onOpenChange}
      busy={busy}
      title="Share for client review"
      description={
        <>
          {clientName} gets a private link to approve posts or ask for changes, with no account
          needed. {campaignName ? "It shows only this campaign's pending posts." : "It shows their pending posts."}{" "}
          Approvals still go through moderation; nothing is posted from the link.
        </>
      }
      footer={
        <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={busy}>
          Done
        </Button>
      }
    >
      <div className="space-y-4">
        {url ? (
          <div className="space-y-2">
            <label htmlFor="review-link-url" className="text-xs font-medium text-muted">
              Link for {scope} · works for 14 days
            </label>
            <div className="flex gap-2">
              <Input id="review-link-url" readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
              <Button onClick={copy} aria-label="Copy link">
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className="text-xs text-muted">
              Copy it now — it can&apos;t be shown again. If it&apos;s lost, make a new one and turn
              the old one off below.
            </p>
          </div>
        ) : (
          <Button onClick={create} disabled={busy}>
            <Link2 className="h-3.5 w-3.5" /> {busy ? "Creating…" : `Create link for ${scope}`}
          </Button>
        )}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}

        <div>
          <p className="text-xs font-medium text-muted">Active links for {clientName}</p>
          {links === null ? (
            <p className="mt-2 text-xs text-muted">Loading…</p>
          ) : active.length === 0 ? (
            <p className="mt-2 text-xs text-muted">None.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line rounded-lg border border-line">
              {active.map((link) => (
                <li key={link.id} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
                  <span className="min-w-0 text-ink">
                    {link.campaign_name ?? "All pending posts"}
                    <span className="block text-muted">
                      Made {relative(link.created_at)} · expires {relative(link.expires_at)}
                      {link.last_used_at ? ` · last opened ${relative(link.last_used_at)}` : " · not opened yet"}
                    </span>
                  </span>
                  <Button size="sm" variant="ghost" onClick={() => revoke(link)}>
                    Turn off
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </PostDialog>
  );
}
