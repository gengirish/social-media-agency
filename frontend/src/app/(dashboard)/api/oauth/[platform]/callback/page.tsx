"use client";

/*
 * Where X / LinkedIn / Facebook send the user back after consent. The backend
 * builds redirect_uri as `${first CORS origin}/api/oauth/<platform>/callback`
 * (routers/oauth.py), so this page must live at exactly that path. It hands
 * the code, the signed state and (for X) the PKCE verifier to the backend,
 * which verifies the state, exchanges the code and stores the encrypted token.
 */

import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/feedback";
import { Eyebrow, Panel } from "@/components/ui/panel";
import { platformName } from "@/components/setup/connected-accounts";
import { useActiveClient } from "@/lib/active-client";
import { clientIdFromState, setupApi, takePkceVerifier } from "@/lib/api-setup";

function Callback() {
  const { platform } = useParams<{ platform: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const { refresh, setActiveId } = useActiveClient();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // a code is single-use; never exchange it twice
    started.current = true;
    const code = params.get("code");
    const state = params.get("state");
    const denied = params.get("error_description") || params.get("error");
    if (denied) {
      setError(`${platformName(platform)} did not grant access: ${denied}`);
      return;
    }
    const clientId = state ? clientIdFromState(state) : null;
    if (!code || !state || !clientId) {
      setError("This sign-in link is incomplete or expired. Start the connection again from Setup › Accounts.");
      return;
    }
    (async () => {
      try {
        await setupApi.completeOAuth(platform, {
          code,
          state,
          client_id: clientId,
          code_verifier: takePkceVerifier(platform),
        });
        setActiveId(clientId);
        await refresh();
        router.replace(`/setup/accounts?connected=${encodeURIComponent(platform)}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "The connection could not be completed.");
      }
    })();
  }, [params, platform, refresh, router, setActiveId]);

  return (
    <Panel className="mx-auto max-w-lg p-8">
      <Eyebrow>Connecting {platformName(platform)}</Eyebrow>
      {error ? (
        <>
          <h1 className="mt-3 font-display text-xl text-ink">The connection didn&apos;t complete.</h1>
          <ErrorBanner message={error} />
          <Link href="/setup/accounts" className={buttonVariants({ variant: "secondary", className: "mt-5" })}>
            Back to Connected accounts
          </Link>
        </>
      ) : (
        <h1 className="mt-3 flex items-center gap-2 font-display text-xl text-ink">
          <Loader2 className="h-4 w-4 animate-spin text-accent-text" /> Finishing the connection…
        </h1>
      )}
    </Panel>
  );
}

export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={null}>
      <Callback />
    </Suspense>
  );
}
