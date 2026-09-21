"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Client } from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { toast } from "sonner";
import { Plus, Users, Globe, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/panel";
import { SectionCard } from "@/components/ui/section-card";
import { Field, Input, Textarea } from "@/components/ui/field";
import { EmptyState, LoadingState } from "@/components/ui/empty-state";

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ brand_name: "", industry: "", description: "", website_url: "", contact_email: "" });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadClients();
  }, []);

  function loadClients() {
    api.getClients().then((res) => setClients(res.items)).catch((err) => toast.error(err.message)).finally(() => setLoading(false));
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await api.createClient(formData);
      trackFeature("client-create");
      toast.success("Client created!");
      setShowForm(false);
      setFormData({ brand_name: "", industry: "", description: "", website_url: "", contact_email: "" });
      loadClients();
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
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Website" htmlFor="website_url">
                <Input id="website_url" value={formData.website_url} onChange={(e) => setFormData(p => ({ ...p, website_url: e.target.value }))} />
              </Field>
              <Field label="Contact Email" htmlFor="contact_email">
                <Input id="contact_email" type="email" value={formData.contact_email} onChange={(e) => setFormData(p => ({ ...p, contact_email: e.target.value }))} />
              </Field>
            </div>
            <div className="flex justify-end gap-2 border-t border-line pt-4">
              <Button variant="secondary" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button type="submit" disabled={creating}>{creating ? "Creating..." : "Create Client"}</Button>
            </div>
          </SectionCard>
        </form>
      )}

      {clients.length === 0 ? (
        <EmptyState icon={Users} title="No clients yet" description="Add your first brand to get started" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {clients.map((client, i) => (
            <div
              key={client.id}
              style={{ animationDelay: `${Math.min(i, 8) * 0.05}s` }}
              className="flex flex-col rounded-xl border border-line bg-panel/70 p-5 shadow-soft backdrop-blur-xl transition-colors duration-200 focus-within:border-accent/50 hover:border-accent/40 motion-safe:animate-screen-in"
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
                    className="font-display font-semibold text-ink transition-colors hover:text-accent-text"
                  >
                    {client.brand_name}
                  </Link>
                  <p className="truncate font-mono text-[11px] text-muted">{client.industry}</p>
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
