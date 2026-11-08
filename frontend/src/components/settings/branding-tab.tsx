"use client";

/*
 * Settings › Branding — what an agency's client sees on a review link and on
 * the cover of a campaign pack: the agency's name, logo and accent colour.
 *
 * Scope, stated on the screen so nobody reads more into it: this brands the
 * two client-facing surfaces and nothing else. There is no custom domain and
 * the app itself is not re-skinned (product rule 1).
 *
 * The logo uploads immediately (`POST /integrations/white-label/logo`) and the
 * rest saves on Save (`PUT /integrations/white-label`). The server reads the
 * MIME from the bytes, caps size and pixels, and refuses SVG; the client-side
 * checks here only save a round trip and never stand in for them.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ImagePlus, Loader2, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  apiErrorMessage,
  LOGO_ACCEPT,
  LOGO_MAX_BYTES,
  LOGO_MAX_EDGE,
  type WhiteLabelBranding,
  type WhiteLabelResponse,
} from "@/lib/api";
import { trackFeature } from "@/lib/analytics";
import { useSession } from "@/lib/session";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/panel";
import { Field, Input } from "@/components/ui/field";
import { Notice } from "@/components/ui/empty-state";

/** The pack's own accent when no colour is set — `campaign_pack.py::_DEFAULT_ACCENT`. */
const DEFAULT_ACCENT = "#1f3a5f";
const HEX = /^#[0-9a-fA-F]{6}$/;

function hasRow(res: WhiteLabelResponse): res is WhiteLabelBranding {
  return "id" in res;
}

function kb(bytes: number): string {
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

interface Form {
  companyName: string;
  color: string;
  supportEmail: string;
  isActive: boolean;
}

function formFrom(res: WhiteLabelResponse): Form {
  if (!hasRow(res)) return { companyName: "", color: "", supportEmail: "", isActive: true };
  return {
    companyName: res.company_name ?? "",
    color: res.primary_color ?? "",
    supportEmail: res.support_email ?? "",
    isActive: res.is_active,
  };
}

export function BrandingTab() {
  const { can, loading: sessionLoading } = useSession();
  const canEdit = can("workspace.manage");
  const [loading, setLoading] = useState(true);
  const [orgName, setOrgName] = useState("");
  const [branding, setBranding] = useState<WhiteLabelResponse>({ is_active: false });
  const [form, setForm] = useState<Form>(formFrom({ is_active: false }));
  const [saved, setSaved] = useState<Form>(form);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [removing, setRemoving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [wl, settings] = await Promise.all([api.getWhiteLabel(), api.getSettings()]);
      setBranding(wl);
      const f = formFrom(wl);
      setForm(f);
      setSaved(f);
      setOrgName(settings.name ?? "");
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e) ?? "Could not load branding");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const dirty =
    form.companyName !== saved.companyName ||
    form.color !== saved.color ||
    form.supportEmail !== saved.supportEmail ||
    form.isActive !== saved.isActive;
  const colorValid = form.color === "" || HEX.test(form.color);
  const logo = hasRow(branding) ? branding : null;
  const shownName = form.companyName.trim() || orgName || "Your agency";
  const accent = HEX.test(form.color) ? form.color : DEFAULT_ACCENT;

  const applyResponse = (res: WhiteLabelResponse) => {
    setBranding(res);
    // The server's view of the switch wins (a first upload turns it on); the
    // text fields keep whatever is being typed.
    if (hasRow(res)) {
      setForm((f) => ({ ...f, isActive: res.is_active }));
      setSaved((f) => ({ ...f, isActive: res.is_active }));
    }
  };

  const handleSave = async () => {
    if (!colorValid) {
      toast.error("The accent colour must be a six-digit hex value, like #1f3a5f.");
      return;
    }
    setSaving(true);
    try {
      const res = await api.updateWhiteLabel({
        company_name: form.companyName,
        primary_color: form.color,
        support_email: form.supportEmail,
        is_active: form.isActive,
      });
      setBranding(res);
      const f = formFrom(res);
      setForm(f);
      setSaved(f);
      trackFeature("branding-save");
      toast.success("Branding saved");
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e) ?? "Could not save branding");
    } finally {
      setSaving(false);
    }
  };

  const handleFile = async (file: File | undefined) => {
    if (fileRef.current) fileRef.current.value = "";
    if (!file) return;
    if (file.size > LOGO_MAX_BYTES) {
      toast.error(
        `That file is ${kb(file.size)}; the limit is ${kb(LOGO_MAX_BYTES)}. Export it smaller, or as a PNG with fewer colours.`
      );
      return;
    }
    setUploading(true);
    try {
      const res = await api.uploadWhiteLabelLogo(file);
      applyResponse(res);
      trackFeature("branding-logo-upload");
      toast.success("Logo uploaded");
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e) ?? "Could not upload the logo");
    } finally {
      setUploading(false);
    }
  };

  const handleRemove = async () => {
    setRemoving(true);
    try {
      applyResponse(await api.deleteWhiteLabelLogo());
      toast.success("Logo removed");
    } catch (e: unknown) {
      toast.error(apiErrorMessage(e) ?? "Could not remove the logo");
    } finally {
      setRemoving(false);
    }
  };

  const busy = saving || uploading || removing;
  const readOnly = !canEdit || busy;

  return (
    <div className="space-y-6">
      <div className="space-y-1.5">
        <Eyebrow>Branding</Eyebrow>
        <h3 className="font-display text-lg font-semibold text-ink">Agency branding</h3>
        <p className="max-w-prose text-sm text-muted">
          What a client sees on a review link and on the cover of a campaign pack: your name, logo
          and accent colour. It changes nothing inside the app, and there is no custom domain.
        </p>
      </div>

      {!sessionLoading && !canEdit && (
        <Notice tone="info" title="Read only">
          Only workspace owners and admins can change branding. What is shown here is what clients
          currently see.
        </Notice>
      )}

      {loading ? (
        <div role="status" className="flex items-center gap-2 font-mono text-xs text-muted">
          <Loader2 className="h-4 w-4 animate-spin text-accent-text" />
          Loading branding…
        </div>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="max-w-md space-y-5">
            {/* Logo: uploads on its own, so the preview is real the moment it lands. */}
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted">Logo</p>
              <div className="flex flex-wrap items-center gap-4">
                <div
                  className="flex h-20 w-40 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-line bg-panel p-2"
                  data-testid="branding-logo-preview"
                >
                  {logo?.logo_data_url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- a data: URI the org just uploaded, not a static asset
                    <img
                      src={logo.logo_data_url}
                      alt="Current logo"
                      className="max-h-full max-w-full object-contain"
                    />
                  ) : (
                    <span className="font-mono text-[11px] text-muted">No logo yet</span>
                  )}
                </div>
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={readOnly}
                      onClick={() => fileRef.current?.click()}
                    >
                      {uploading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <ImagePlus className="h-4 w-4" />
                      )}
                      {logo?.has_logo ? "Replace logo" : "Upload logo"}
                    </Button>
                    {logo?.has_logo && (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={readOnly}
                        onClick={() => void handleRemove()}
                      >
                        {removing ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                        Remove
                      </Button>
                    )}
                  </div>
                  <p className="text-xs text-muted">
                    {logo?.has_logo && logo.logo_mime && logo.logo_bytes != null ? (
                      <span className="font-mono">
                        {logo.logo_mime.replace("image/", "").toUpperCase()} · {kb(logo.logo_bytes)}
                      </span>
                    ) : (
                      <>
                        PNG, JPEG or WebP, up to {kb(LOGO_MAX_BYTES)} and {LOGO_MAX_EDGE} px. It is
                        shown about 40 px high.
                      </>
                    )}
                  </p>
                </div>
              </div>
              <input
                ref={fileRef}
                id="branding-logo-file"
                type="file"
                accept={LOGO_ACCEPT}
                className="sr-only"
                aria-label="Choose a logo file"
                disabled={readOnly}
                onChange={(e) => void handleFile(e.target.files?.[0])}
              />
            </div>

            <Field
              label="Agency name"
              htmlFor="branding-company-name"
              hint={`Blank uses your workspace name${orgName ? ` (${orgName})` : ""}. It appears as “Prepared by …” on the pack.`}
            >
              <Input
                id="branding-company-name"
                type="text"
                value={form.companyName}
                maxLength={255}
                placeholder={orgName || "Northwind Social"}
                disabled={readOnly}
                onChange={(e) => setForm((f) => ({ ...f, companyName: e.target.value }))}
              />
            </Field>

            <Field
              label="Accent colour"
              htmlFor="branding-color"
              hint="The bar across the top of the review page and the pack's headings. Blank uses the pack's own navy."
              error={colorValid ? undefined : "Use a six-digit hex value, like #1f3a5f."}
            >
              <div className="flex items-center gap-2">
                <input
                  id="branding-color-picker"
                  type="color"
                  aria-label="Pick an accent colour"
                  value={accent}
                  disabled={readOnly}
                  className="h-10 w-12 cursor-pointer rounded-md border border-line bg-panel p-1 disabled:cursor-not-allowed"
                  onChange={(e) => setForm((f) => ({ ...f, color: e.target.value }))}
                />
                <Input
                  id="branding-color"
                  type="text"
                  value={form.color}
                  placeholder={DEFAULT_ACCENT}
                  maxLength={7}
                  spellCheck={false}
                  disabled={readOnly}
                  className="font-mono"
                  onChange={(e) => setForm((f) => ({ ...f, color: e.target.value.trim() }))}
                />
              </div>
            </Field>

            <Field
              label="Support email"
              htmlFor="branding-support-email"
              hint="Optional. Shown at the foot of the review page so a client can reach you."
            >
              <Input
                id="branding-support-email"
                type="email"
                value={form.supportEmail}
                maxLength={255}
                placeholder="hello@northwind.social"
                disabled={readOnly}
                onChange={(e) => setForm((f) => ({ ...f, supportEmail: e.target.value }))}
              />
            </Field>

            <label className="flex items-start gap-2.5 text-sm text-ink">
              <input
                id="branding-is-active"
                type="checkbox"
                checked={form.isActive}
                disabled={readOnly}
                className="mt-0.5 h-4 w-4 accent-[rgb(var(--c-accent))]"
                onChange={(e) => setForm((f) => ({ ...f, isActive: e.target.checked }))}
              />
              <span>
                <span className="font-medium">Show this branding to clients</span>
                <span className="mt-0.5 block text-xs text-muted">
                  Off, clients see your workspace name and no logo — on review links and packs
                  alike.
                </span>
              </span>
            </label>

            <div className="border-t border-line pt-5">
              <Button disabled={readOnly || !dirty || !colorValid} onClick={() => void handleSave()}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                Save branding
              </Button>
            </div>
          </div>

          {/* How it looks: the pack cover, drawn from the form as it is being typed. */}
          <aside className="space-y-2 lg:pt-6" aria-label="Preview">
            <p className="text-xs font-medium text-muted">How clients see it</p>
            <div
              className="overflow-hidden rounded-lg border border-line bg-panel"
              data-testid="branding-preview"
            >
              <div className="h-1.5" style={{ backgroundColor: form.isActive ? accent : DEFAULT_ACCENT }} />
              <div className="space-y-3 p-4">
                <div className="flex min-h-[2.5rem] items-center gap-2.5">
                  {form.isActive && logo?.logo_data_url && (
                    // eslint-disable-next-line @next/next/no-img-element -- data: URI preview
                    <img
                      src={logo.logo_data_url}
                      alt=""
                      className="h-8 max-w-[120px] object-contain"
                    />
                  )}
                  <span className="truncate text-sm font-semibold text-ink">
                    {form.isActive ? shownName : orgName || "Your workspace"}
                  </span>
                </div>
                <p className="font-mono text-[10px] uppercase tracking-wider text-muted">
                  Campaign pack
                </p>
                <p className="font-display text-base font-semibold leading-tight text-ink">
                  Cold Brew Launch
                </p>
                <p className="text-xs text-muted">
                  Prepared by {form.isActive ? shownName : orgName || "your workspace"}
                </p>
              </div>
            </div>
            <p className="text-xs text-muted">
              The pack cover, as a client opens it. The review link uses the same name, logo and
              colour bar.
            </p>
          </aside>
        </div>
      )}
    </div>
  );
}
