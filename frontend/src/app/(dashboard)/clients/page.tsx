"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Client } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Users, Loader2, Globe, Mail, Building2 } from "lucide-react";
import { cn } from "@/lib/utils";

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
      toast.success("Client created!");
      setShowForm(false);
      setFormData({ brand_name: "", industry: "", description: "", website_url: "", contact_email: "" });
      loadClients();
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return <div className="flex h-64 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-indigo-600" /></div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Clients</h1>
          <p className="mt-1 text-slate-500">Manage your brands and their profiles</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500">
          <Plus className="h-4 w-4" /> Add Client
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
          <h3 className="text-lg font-semibold text-slate-900">New Client</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="brand_name" className="mb-1 block text-sm font-medium text-slate-700">Brand Name *</label>
              <input id="brand_name" value={formData.brand_name} onChange={(e) => setFormData(p => ({ ...p, brand_name: e.target.value }))} required className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" />
            </div>
            <div>
              <label htmlFor="industry" className="mb-1 block text-sm font-medium text-slate-700">Industry *</label>
              <input id="industry" value={formData.industry} onChange={(e) => setFormData(p => ({ ...p, industry: e.target.value }))} required className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" />
            </div>
          </div>
          <div>
            <label htmlFor="description" className="mb-1 block text-sm font-medium text-slate-700">Description</label>
            <textarea id="description" value={formData.description} onChange={(e) => setFormData(p => ({ ...p, description: e.target.value }))} rows={2} className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 resize-none" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="website_url" className="mb-1 block text-sm font-medium text-slate-700">Website</label>
              <input id="website_url" value={formData.website_url} onChange={(e) => setFormData(p => ({ ...p, website_url: e.target.value }))} className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" />
            </div>
            <div>
              <label htmlFor="contact_email" className="mb-1 block text-sm font-medium text-slate-700">Contact Email</label>
              <input id="contact_email" type="email" value={formData.contact_email} onChange={(e) => setFormData(p => ({ ...p, contact_email: e.target.value }))} className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500" />
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <button type="button" onClick={() => setShowForm(false)} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">Cancel</button>
            <button type="submit" disabled={creating} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50">{creating ? "Creating..." : "Create Client"}</button>
          </div>
        </form>
      )}

      {clients.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 py-16">
          <Users className="mb-4 h-12 w-12 text-slate-300" />
          <h3 className="text-lg font-semibold text-slate-900">No clients yet</h3>
          <p className="mt-1 text-slate-500">Add your first brand to get started</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {clients.map((client) => (
            <div key={client.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50">
                  <Building2 className="h-5 w-5 text-indigo-600" />
                </div>
                <div className="min-w-0 flex-1">
                  <Link
                    href={`/clients/${client.id}`}
                    className="font-semibold text-slate-900 hover:text-indigo-600"
                  >
                    {client.brand_name}
                  </Link>
                  <p className="text-sm text-slate-500">{client.industry}</p>
                </div>
              </div>
              {client.description && (
                <p className="mt-3 line-clamp-2 text-sm text-slate-600">{client.description}</p>
              )}
              <div className="mt-4 flex items-center gap-4 text-sm text-slate-400">
                {client.website_url && <div className="flex items-center gap-1"><Globe className="h-3.5 w-3.5" /> Website</div>}
                {client.contact_email && <div className="flex items-center gap-1"><Mail className="h-3.5 w-3.5" /> Email</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
