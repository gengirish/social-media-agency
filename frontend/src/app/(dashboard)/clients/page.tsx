"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type BrandProfile, type Client } from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { toast } from "sonner";
import { Plus, Users, Globe, Mail, Sparkles, Loader2, X, Archive } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/panel";
import { SectionCard } from "@/components/ui/section-card";
import { Field, Input, Textarea } from "@/components/ui/field";
import { EmptyState, LoadingState } from "@/components/ui/empty-state";
import { SegmentedTabs } from "@/components/ui/tabs";

const EMPTY_FORM = { brand_name: "", industry: "", description: "", website_url: "", contact_email: "" };
type ClientForm = typeof EMPTY_FORM;
type ClientView = "active" | "archived";
// The fields a website read may fill. Website and email stay the user's.
const READ_FIELDS = ["brand_name", "industry", "description"] as const;

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<ClientView>("active");
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState<ClientForm>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [reading, setReading] = useState(false);
  const [profile, setProfile] = useState<BrandProfile | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  // What the last read wrote into each field, so a second read can replace
  // its own values without clobbering anything the user typed.
  const lastRead = useRef<Partial<ClientForm>>({});

  useEffect(() => {
    let cancelled = false;
    api
      .getClients(1, view === "archived")
      .then((res) => !cancelled && setClients(res.items))
      .catch((err) => !cancelled && toast.error(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [view]);

  function loadClients() {
    api
      .getClients(1, view === "archived")
      .then((res) => setClients(res.items))
      .catch((err) => toast.error(err.message));
  }

  function resetForm() {
    setFormData(EMPTY_FORM);
    setProfile(null);
    setOverwrite(false);
    lastRead.current = {};
  }

  async function handleReadWebsite() {
    const url = formData.website_url.trim();
    if (!url) {
      toast.error("Enter the brand's website first");
      return;
    }
    setReading(true);
    try {
      const data = await api.extractBrand(url);
      if (data.error) {
        toast.error(data.error);
        return;
      }
      const filled: Partial<ClientForm> = {};
      const next = { ...formData };
      for (const key of READ_FIELDS) {
        const value = data[key]?.trim();
        const untouched = !formData[key] || formData[key] === lastRead.current[key];
        if (value && (overwrite || untouched)) {
          next[key] = value;
          filled[key] = value;
        }
      }
      setFormData(next);
      lastRead.current = filled;
      setProfile(data);
      trackFeature("client-website-read");
      toast.success("Website read. Review the details before creating.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not read the website");
    } finally {
      setReading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      const client = await api.createClient(formData);
      trackFeature("client-create", { from_website_read: !!profile });
      if (profile) {
        try {
          await api.createBrandProfile(client.id, {
            voice_description: profile.voice_description || "",
            tone_attributes: profile.tone_attributes ?? {},
            target_audience: profile.target_audience || "",
            style_rules: Array.isArray(profile.style_rules) ? profile.style_rules : [],
            vocabulary_include: Array.isArray(profile.vocabulary_include) ? profile.vocabulary_include : [],
            vocabulary_exclude: Array.isArray(profile.vocabulary_exclude) ? profile.vocabulary_exclude : [],
            emoji_policy: profile.emoji_policy || "minimal",
            competitor_differentiation: profile.competitor_differentiation || "",
          });
          toast.success("Client created with brand profile");
        } catch (err) {
          toast.warning(
            `Client created, but the brand profile could not be saved: ${err instanceof Error ? err.message : String(err)}`
          );
        }
      } else {
        toast.success("Client created!");
      }
      setShowForm(false);
      resetForm();
      if (view === "active") loadClients();
      else setView("active");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return <LoadingState label="Loading clients" />;
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Setup"
        title="Clients"
        description="Manage your brands and their profiles"
        actions={
          <Button onClick={() => setShowForm(!showForm)} aria-expanded={showForm}>
            <Plus className="h-4 w-4" /> Add Client
          </Button>
        }
      />

      {showForm && (
        <form onSubmit={handleCreate}>
          <SectionCard eyebrow="Onboard a brand" title={<span className="text-lg">New Client</span>} bodyClassName="space-y-4">
            <Field label="Website" htmlFor="website_url">
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  id="website_url"
                  value={formData.website_url}
                  onChange={(e) => setFormData(p => ({ ...p, website_url: e.target.value }))}
                  placeholder="https://acme.com"
                  className="font-mono"
                />
                <Button variant="secondary" onClick={handleReadWebsite} disabled={reading || !formData.website_url.trim()} className="shrink-0">
                  {reading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  {reading ? "Reading…" : "Read website"}
                </Button>
              </div>
              <p className="mt-1.5 text-xs text-muted">
                AI reads the site and drafts the name, industry, description and brand voice. You review everything before it is saved.
              </p>
              <label className="mt-2 flex w-fit cursor-pointer items-center gap-2 text-xs text-muted">
                <input
                  type="checkbox"
                  checked={overwrite}
                  onChange={(e) => setOverwrite(e.target.checked)}
                  className="h-3.5 w-3.5 accent-[rgb(var(--c-accent))]"
                />
                Replace details I&apos;ve already typed
              </label>
            </Field>
            {profile && (
              <div className="relative rounded-lg border border-accent/40 bg-accent/5 p-4 pr-10 text-sm" role="status">
                <button
                  type="button"
                  onClick={() => setProfile(null)}
                  aria-label="Discard the brand profile from the website read"
                  className="absolute right-2 top-2 rounded p-1 text-muted hover:text-ink"
                >
                  <X className="h-4 w-4" />
                </button>
                <p className="font-mono text-[11px] text-muted">Brand profile from website, saved with the client</p>
                <dl className="mt-2 grid gap-2 sm:grid-cols-2">
                  <div>
                    <dt className="text-xs text-muted">Voice</dt>
                    <dd className="text-ink">{profile.voice_description || "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Target audience</dt>
                    <dd className="text-ink">{profile.target_audience || "—"}</dd>
                  </div>
                </dl>
              </div>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Brand Name *" htmlFor="brand_name">
                <Input id="brand_name" value={formData.brand_name} onChange={(e) => setFormData(p => ({ ...p, brand_name: e.target.value }))} required />
              </Field>
              <Field label="Industry *" htmlFor="industry">
                <Input id="industry" value={formData.industry} onChange={(e) => setFormData(p => ({ ...p, industry: e.target.value }))} required />
              </Field>
            </div>
            <Field label="Description" htmlFor="description">
              <Textarea id="description" value={formData.description} onChange={(e) => setFormData(p => ({ ...p, description: e.target.value }))} rows={2} />
            </Field>
            <Field label="Contact Email" htmlFor="contact_email">
              <Input id="contact_email" type="email" value={formData.contact_email} onChange={(e) => setFormData(p => ({ ...p, contact_email: e.target.value }))} />
            </Field>
            <div className="flex justify-end gap-2 border-t border-line pt-4">
              <Button variant="secondary" onClick={() => { setShowForm(false); resetForm(); }}>Cancel</Button>
              <Button type="submit" disabled={creating || reading}>{creating ? "Creating..." : "Create Client"}</Button>
            </div>
          </SectionCard>
        </form>
      )}

      <SegmentedTabs
        label="Client status"
        items={[
          { id: "active", label: "Active", icon: Users },
          { id: "archived", label: "Archived", icon: Archive },
        ]}
        value={view}
        onChange={setView}
      />

      {clients.length === 0 ? (
        view === "archived" ? (
          <EmptyState icon={Archive} title="No archived clients" description="Clients you archive are kept here and can be restored" />
        ) : (
          <EmptyState icon={Users} title="No clients yet" description="Add your first brand to get started" />
        )
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {clients.map((client, i) => (
            <div
              key={client.id}
              style={{ animationDelay: `${Math.min(i, 8) * 0.05}s` }}
              className="group relative flex cursor-pointer flex-col rounded-xl border border-line bg-panel/70 p-5 shadow-soft backdrop-blur-xl transition-colors duration-200 focus-within:border-accent/50 hover:border-accent/40 motion-safe:animate-screen-in"
            >
              <div className="flex items-center gap-3">
                <div
                  aria-hidden
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-accent/40 bg-accent/10 font-display text-sm font-semibold text-accent-text"
                >
                  {client.brand_name.slice(0, 2).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <Link
                    href={`/clients/${client.id}`}
                    // after:inset-0 stretches the link's hit area over the whole tile.
                    className="font-display font-semibold text-ink transition-colors after:absolute after:inset-0 after:rounded-xl after:content-[''] focus-visible:outline-none group-hover:text-accent-text"
                  >
                    {client.brand_name}
                  </Link>
                  <p className="truncate font-mono text-[11px] text-muted">
                    {client.industry}
                    {!client.is_active && " · Archived"}
                  </p>
                </div>
              </div>
              {client.description && (
                <p className="mt-3 line-clamp-2 text-sm text-muted">{client.description}</p>
              )}
              {(client.website_url || client.contact_email) && (
                <div className="mt-4 flex items-center gap-4 border-t border-line pt-3 font-mono text-[11px] text-muted">
                  {client.website_url && <div className="flex items-center gap-1"><Globe className="h-3.5 w-3.5" /> Website</div>}
                  {client.contact_email && <div className="flex items-center gap-1"><Mail className="h-3.5 w-3.5" /> Email</div>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
