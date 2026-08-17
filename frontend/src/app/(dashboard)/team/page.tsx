"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Loader2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api, type TeamMember } from "@/lib/api";

const ROLES = [
  { value: "admin", label: "Admin" },
  { value: "manager", label: "Manager" },
  { value: "content_creator", label: "Content creator" },
  { value: "viewer", label: "Viewer" },
];

function roleBadgeClass(role: string) {
  const r = role.toLowerCase();
  if (r === "admin") return "bg-violet-100 text-violet-800";
  if (r === "manager") return "bg-indigo-100 text-indigo-800";
  if (r === "content_creator") return "bg-sky-100 text-sky-800";
  if (r === "viewer") return "bg-slate-100 text-slate-700";
  return "bg-slate-100 text-slate-700";
}

function initials(name: string, email: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  if (parts.length === 1 && parts[0].length >= 2) return parts[0].slice(0, 2).toUpperCase();
  if (email) return email.slice(0, 2).toUpperCase();
  return "?";
}

export default function TeamPage() {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("content_creator");
  const [inviting, setInviting] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const list = await api.getTeam();
      setMembers(list);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to load team");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      const res = await api.inviteTeamMember(inviteEmail.trim(), inviteRole);
      // The backend only sends an email when AgentMail is configured for this
      // org. Report what it actually did — the old copy always said "Invitation
      // sent", which was usually false.
      const emailed = res.message?.includes("Invitation email sent");
      if (emailed) {
        toast.success(res.message);
      } else {
        toast.warning(res.message ?? "User created, but no invitation email was sent.", {
          description: res.temp_password
            ? `Temporary password: ${res.temp_password}`
            : undefined,
          duration: 30000,
        });
      }
      setInviteEmail("");
      setShowInvite(false);
      load();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Invite failed");
    } finally {
      setInviting(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Team</h1>
          <p className="mt-1 text-slate-500">Members in your organization</p>
        </div>
        <button
          type="button"
          onClick={() => setShowInvite((v) => !v)}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500"
        >
          <UserPlus className="h-4 w-4" />
          Invite Member
        </button>
      </div>

      {showInvite && (
        <form
          onSubmit={handleInvite}
          className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4"
        >
          <h2 className="text-lg font-semibold text-slate-900">Invite a teammate</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
              <input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
                placeholder="colleague@company.com"
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Role</label>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-slate-900 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowInvite(false)}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={inviting}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {inviting ? "Sending…" : "Send invite"}
            </button>
          </div>
        </form>
      )}

      {/* `services/team.py::check_permission` exists but no route calls it, so a
          role badge is a label, not a restriction. Say so rather than let the
          badge imply enforced access control. */}
      <div className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
        <p className="text-sm text-amber-900">
          <span className="font-medium">Roles are not enforced yet.</span> Every member of this
          organization can currently read and change everything in it — the role shown below is a
          label only. Invite people accordingly.
        </p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <ul className="divide-y divide-slate-100">
          {members.length === 0 ? (
            <li className="px-6 py-12 text-center text-sm text-slate-500">No team members yet</li>
          ) : (
            members.map((m) => (
              <li key={m.id} className="flex items-center gap-4 px-6 py-4">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-sm font-bold text-indigo-700">
                  {initials(m.full_name, m.email)}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-slate-900 truncate">{m.full_name}</p>
                  <p className="text-sm text-slate-500 truncate">{m.email}</p>
                </div>
                <span
                  className={cn(
                    "shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold capitalize",
                    roleBadgeClass(m.role)
                  )}
                >
                  {m.role.replace("_", " ")}
                </span>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
