"use client";

import { useState } from "react";
import { toast } from "sonner";
import { api, type Client, type SavedBrandProfile } from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import { Field, Input, Select, Textarea } from "@/components/ui/field";

const EMOJI_POLICIES = ["none", "minimal", "moderate", "heavy"] as const;

function toList(text: string, separator: RegExp): string[] {
  return text
    .split(separator)
    .map((s) => s.trim())
    .filter(Boolean);
}

function initialState(client: Client, profile: SavedBrandProfile | null) {
  return {
    brand_name: client.brand_name,
    industry: client.industry ?? "",
    description: client.description ?? "",
    website_url: client.website_url ?? "",
    contact_email: client.contact_email ?? "",
    voice_description: profile?.voice_description ?? "",
    target_audience: profile?.target_audience ?? "",
    competitor_differentiation: profile?.competitor_differentiation ?? "",
    emoji_policy: profile?.emoji_policy || "moderate",
    vocabulary_include: (profile?.vocabulary_include ?? []).join(", "),
    vocabulary_exclude: (profile?.vocabulary_exclude ?? []).join(", "),
    style_rules: (profile?.style_rules ?? []).join("\n"),
  };
}

type FormState = ReturnType<typeof initialState>;
const BRAND_FIELDS = [
  "voice_description",
  "target_audience",
  "competitor_differentiation",
  "emoji_policy",
  "vocabulary_include",
  "vocabulary_exclude",
  "style_rules",
] as const;

export function EditClientForm({
  client,
  profile,
  onCancel,
  onSaved,
}: {
  client: Client;
  profile: SavedBrandProfile | null;
  onCancel: () => void;
  onSaved: (client: Client, profile: SavedBrandProfile | null) => void;
}) {
  const [initial] = useState(() => initialState(client, profile));
  const [form, setForm] = useState<FormState>(initial);
  const [saving, setSaving] = useState(false);

  const set = (key: keyof FormState) => (e: { target: { value: string } }) =>
    setForm((p) => ({ ...p, [key]: e.target.value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await api.updateClient(client.id, {
        brand_name: form.brand_name.trim(),
        industry: form.industry.trim(),
        description: form.description.trim(),
        website_url: form.website_url.trim(),
        contact_email: form.contact_email.trim(),
      });

      // Only touch the brand profile if it exists or the user changed a brand field,
      // so saving basic details never creates an empty profile as a side effect.
      const brandChanged = BRAND_FIELDS.some((k) => form[k] !== initial[k]);
      let savedProfile = profile;
      if (profile || brandChanged) {
        try {
          savedProfile = await api.saveBrandProfile(client.id, {
            voice_description: form.voice_description.trim(),
            target_audience: form.target_audience.trim(),
            competitor_differentiation: form.competitor_differentiation.trim(),
            emoji_policy: form.emoji_policy,
            vocabulary_include: toList(form.vocabulary_include, /,/),
            vocabulary_exclude: toList(form.vocabulary_exclude, /,/),
            style_rules: toList(form.style_rules, /\n/),
          });
        } catch (err) {
          toast.warning(
            `Client details saved, but the brand voice could not be saved: ${err instanceof Error ? err.message : String(err)}`
          );
          onSaved(updated, profile);
          return;
        }
      }
      trackFeature("client-edit", { brand_changed: brandChanged });
      toast.success("Client updated");
      onSaved(updated, savedProfile);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <SectionCard eyebrow="Edit" title="Client details" bodyClassName="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Brand Name *" htmlFor="edit_brand_name">
            <Input id="edit_brand_name" value={form.brand_name} onChange={set("brand_name")} required minLength={2} />
          </Field>
          <Field label="Industry *" htmlFor="edit_industry">
            <Input id="edit_industry" value={form.industry} onChange={set("industry")} required minLength={2} />
          </Field>
          <Field label="Website" htmlFor="edit_website_url">
            <Input
              id="edit_website_url"
              value={form.website_url}
              onChange={set("website_url")}
              placeholder="https://acme.com"
              className="font-mono"
            />
          </Field>
          <Field label="Contact Email" htmlFor="edit_contact_email">
            <Input id="edit_contact_email" type="email" value={form.contact_email} onChange={set("contact_email")} />
          </Field>
        </div>
        <Field label="Description" htmlFor="edit_description">
          <Textarea id="edit_description" value={form.description} onChange={set("description")} rows={3} />
        </Field>
      </SectionCard>

      <SectionCard eyebrow="Voice" title="Brand voice" bodyClassName="space-y-4">
        <Field label="Voice" htmlFor="edit_voice_description" hint="How the brand sounds. Every agent writes to this.">
          <Textarea id="edit_voice_description" value={form.voice_description} onChange={set("voice_description")} rows={3} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Target audience" htmlFor="edit_target_audience">
            <Textarea id="edit_target_audience" value={form.target_audience} onChange={set("target_audience")} rows={2} />
          </Field>
          <Field label="What sets it apart from competitors" htmlFor="edit_competitor_differentiation">
            <Textarea
              id="edit_competitor_differentiation"
              value={form.competitor_differentiation}
              onChange={set("competitor_differentiation")}
              rows={2}
            />
          </Field>
          <Field label="Words to use" htmlFor="edit_vocabulary_include" hint="Comma-separated">
            <Input id="edit_vocabulary_include" value={form.vocabulary_include} onChange={set("vocabulary_include")} />
          </Field>
          <Field
            label="Words to avoid"
            htmlFor="edit_vocabulary_exclude"
            hint="Comma-separated. Posts containing these are flagged at approval."
          >
            <Input id="edit_vocabulary_exclude" value={form.vocabulary_exclude} onChange={set("vocabulary_exclude")} />
          </Field>
          <Field label="Emoji use" htmlFor="edit_emoji_policy">
            <Select id="edit_emoji_policy" value={form.emoji_policy} onChange={set("emoji_policy")}>
              {EMOJI_POLICIES.map((p) => (
                <option key={p} value={p} className="capitalize">
                  {p}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Style rules" htmlFor="edit_style_rules" hint="One rule per line">
          <Textarea id="edit_style_rules" value={form.style_rules} onChange={set("style_rules")} rows={3} />
        </Field>
      </SectionCard>

      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" disabled={saving}>
          {saving ? "Saving..." : "Save changes"}
        </Button>
      </div>
    </form>
  );
}
