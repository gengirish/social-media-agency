"use client";

/*
 * Settings › API & webhooks: outbound webhooks — how approved posts reach the
 * scheduler an agency already uses (docs/features/integrations.md, "Hand-off to
 * your scheduler").
 *
 * The routes and the dispatcher existed before this panel; nothing in the app
 * could register an endpoint, so the hand-off was API-only. The signing secret is
 * returned once by the server and shown once here.
 */

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage, type Webhook, type WebhookEvent } from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/panel";
import { Field, Input } from "@/components/ui/field";

const EVENT_LABELS: Record<WebhookEvent, string> = {
  "content.approved": "A post is approved (in the Queue or by a client)",
  "campaign.completed": "A campaign pipeline finishes",
};

/** A secret or key the server returns exactly once. Copy it now or make another. */
export function ShownOnce({ label, value, onDismiss }: { label: string; value: string; onDismiss: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-2 rounded-lg border border-amber-300/70 bg-amber-50 p-4">
      <p className="text-sm font-medium text-amber-900">{label}</p>
      <div className="flex gap-2">
        <Input readOnly value={value} className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
        <Button
          size="sm"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
              setCopied(true);
            } catch {
              toast.error("Couldn't copy — select it and copy by hand.");
            }
          }}
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <p className="text-xs text-amber-900">
        This is the only time it is shown. If you lose it, delete it and create a new one.{" "}
        <button type="button" className="underline" onClick={onDismiss}>
          I&apos;ve saved it
        </button>
      </p>
    </div>
  );
}

export function WebhooksPanel() {
  const [hooks, setHooks] = useState<Webhook[] | null>(null);
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<WebhookEvent[]>(["content.approved"]);
  const [busy, setBusy] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .getWebhooks()
      .then((res) => setHooks(res.items))
      .catch(() => setHooks([]));
  }, []);

  useEffect(load, [load]);

  async function add() {
    if (!url.trim() || events.length === 0) return;
    setBusy(true);
    try {
      const made = await api.createWebhook(url.trim(), events);
      setSecret(made.secret);
      setUrl("");
      trackFeature("webhook-create", { events: events.join(",") });
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err) ?? "Couldn't add that webhook.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(hook: Webhook) {
    if (!window.confirm(`Delete the webhook to ${hook.url}? Deliveries stop immediately.`)) return;
    try {
      await api.deleteWebhook(hook.id);
      toast.success("Webhook deleted");
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err) ?? "Couldn't delete that webhook.");
    }
  }

  const toggle = (event: WebhookEvent) =>
    setEvents((prev) => (prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]));

  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <Eyebrow>Hand-off</Eyebrow>
        <h3 className="font-display text-lg font-semibold text-ink">Webhooks</h3>
        <p className="max-w-2xl text-sm text-muted">
          Send each approved post — copy, hashtags, image links, client — to a URL you choose, such as a
          Zapier, Make or n8n catch hook that creates the post in your scheduler. Every request is signed:
          <code className="mx-1 font-mono text-xs">X-Webhook-Signature: sha256=…</code>
          is an HMAC of the body with this webhook&apos;s secret.
        </p>
      </div>

      {secret && (
        <ShownOnce label="Signing secret for the new webhook" value={secret} onDismiss={() => setSecret(null)} />
      )}

      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <Field label="Endpoint URL" htmlFor="webhook-url">
          <Input
            id="webhook-url"
            type="url"
            placeholder="https://hooks.zapier.com/…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </Field>
        <Button onClick={add} disabled={busy || !url.trim() || events.length === 0}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Add webhook
        </Button>
      </div>
      <fieldset className="space-y-1.5">
        <legend className="text-xs font-medium text-muted">Send when</legend>
        {(Object.keys(EVENT_LABELS) as WebhookEvent[]).map((event) => (
          <label key={event} className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={events.includes(event)}
              onChange={() => toggle(event)}
              className="h-4 w-4 accent-[rgb(var(--c-accent))]"
            />
            {EVENT_LABELS[event]} <code className="font-mono text-[11px] text-muted">{event}</code>
          </label>
        ))}
      </fieldset>

      {hooks === null ? (
        <p className="text-sm text-muted">Loading webhooks…</p>
      ) : hooks.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-canvas/40 p-6 text-center text-sm text-muted">
          No webhooks yet.
        </div>
      ) : (
        <ul className="divide-y divide-line rounded-lg border border-line">
          {hooks.map((hook) => (
            <li key={hook.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
              <div className="min-w-0">
                <p className="truncate font-mono text-xs text-ink">{hook.url}</p>
                <p className="mt-1 font-mono text-[11px] text-muted">{hook.events.join(", ")}</p>
              </div>
              <button
                type="button"
                aria-label={`Delete webhook to ${hook.url}`}
                className="press-scale rounded-md p-2 text-muted transition-colors hover:bg-red-50 hover:text-red-600"
                onClick={() => void remove(hook)}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
