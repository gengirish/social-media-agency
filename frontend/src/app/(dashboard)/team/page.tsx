"use client";

import { useEffect, useState } from "react";
import { UserPlus } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api, type TeamInviteResponse, type TeamMember } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Eyebrow, PageHeader } from "@/components/ui/panel";
import { SectionCard } from "@/components/ui/section-card";
import { Field, Input, Select } from "@/components/ui/field";
import { LoadingState, Notice } from "@/components/ui/empty-state";

const ROLES = [
  { value: "admin", label: "Admin" },
  { value: "manager", label: "Manager" },
  { value: "content_creator", label: "Content creator" },
  { value: "viewer", label: "Viewer" },
];

function roleBadgeClass(role: string) {
  const r = role.toLowerCase();
  if (r === "admin") return "border-violet-200 bg-violet-50 text-violet-700";
  if (r === "manager") return "border-indigo-300 bg-indigo-50 text-accent-text";
  if (r === "content_creator") return "border-sky-200 bg-sky-50 text-sky-700";
  if (r === "viewer") return "border-line bg-slate-100 text-slate-600";
  return "border-line bg-slate-100 text-slate-600";
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
  const [resending, setResending] = useState<string | null>(null);

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

  // The backend sends only when AgentMail is configured and has a usable sender
  // inbox. Trust its `email_sent` flag rather than sniffing the display copy,
  // which is free to change wording.
  function reportInviteResult(res: TeamInviteResponse) {
    if (res.email_sent) {
      toast.success(res.message);
      return;
    }
    toast.warning(res.message ?? "User created, but no invitation email was sent.", {
      description: res.temp_password ? `Temporary password: ${res.temp_password}` : undefined,
      duration: 30000,
    });
  }

  async function handleResend(userId: string) {
    setResending(userId);
    try {
      reportInviteResult(await api.resendTeamInvite(userId));
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Resend failed");
    } finally {
      setResending(null);
    }
  }

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      reportInviteResult(await api.inviteTeamMember(inviteEmail.trim(), inviteRole));
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
    return <LoadingState label="Loading team" />;
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Settings"
        title="Team"
        description="Members in your organization"
        actions={
          <Button onClick={() => setShowInvite((v) => !v)} aria-expanded={showInvite}>
            <UserPlus className="h-4 w-4" />
            Invite Member
          </Button>
        }
      />

      {showInvite && (
        <form onSubmit={handleInvite}>
          <SectionCard eyebrow="Invite" title="Invite a teammate" bodyClassName="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Email" htmlFor="invite-email">
                <Input
                  id="invite-email"
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                  placeholder="colleague@company.com"
                />
              </Field>
              <Field label="Role" htmlFor="invite-role">
                <Select id="invite-role" value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}>
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <div className="flex justify-end gap-2 border-t border-line pt-4">
              <Button variant="secondary" onClick={() => setShowInvite(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={inviting}>
                {inviting ? "Sending…" : "Send invite"}
              </Button>
            </div>
          </SectionCard>
        </form>
      )}

      {/* CF-17: this said roles were not enforced, which stopped being true. The
          gate is `require_cap` on the routers, driven by the matrix in
          `backend/permissions.py` — the role is read from the database on every
          gated request, so a demotion takes effect immediately. Keep this summary
          in step with that matrix. */}
      <Notice tone="info">
        <span className="font-medium">What each role can do.</span> Everyone can see the
        workspace and draft content. <strong>Member</strong> adds running campaigns and approving
        posts. <strong>Admin</strong> adds publishing, connecting social accounts, managing the
        team, and workspace administration — API keys, archiving clients, posting preferences.
        <strong> Owner</strong> adds billing. A <strong>viewer</strong> can only read.
      </Notice>

      <div className="overflow-hidden rounded-xl border border-line bg-panel/70 shadow-soft backdrop-blur-xl">
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <Eyebrow>Members</Eyebrow>
          <span className="font-mono text-[11px] text-muted">{members.length}</span>
        </div>
        <ul className="divide-y divide-line">
          {members.length === 0 ? (
            <li className="px-6 py-12 text-center text-sm text-muted">No team members yet</li>
          ) : (
            members.map((m, i) => (
              <li
                key={m.id}
                style={{ animationDelay: `${Math.min(i, 10) * 0.04}s` }}
                className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-slate-500/5 motion-safe:animate-screen-in"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-accent/40 bg-accent/10 font-display text-sm font-semibold text-accent-text">
                  {initials(m.full_name, m.email)}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-ink">{m.full_name}</p>
                  <p className="truncate font-mono text-xs text-muted">{m.email}</p>
                </div>
                <span
                  className={cn(
                    "shrink-0 rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-medium capitalize",
                    roleBadgeClass(m.role)
                  )}
                >
                  {m.role.replace("_", " ")}
                </span>
                {/* Re-inviting through the invite form is impossible — the account
                    already exists, so /team/invite 400s. This is the only route
                    back for someone whose invitation email never arrived. */}
                <Button
                  variant="secondary"
                  onClick={() => handleResend(m.id)}
                  disabled={resending === m.id}
                  title="Rotate the temporary password and email the invite again"
                >
                  {resending === m.id ? "Sending…" : "Resend invite"}
                </Button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
