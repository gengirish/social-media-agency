"use client";

import { useCallback, useEffect, useState } from "react";
import { api, isGenerationQuotaError } from "@/lib/api";

/** generations_used / generations_limit for QuotaHint. Unknown stays null — never a guessed number. */
export function useGenerationQuota() {
  const [used, setUsed] = useState<number | null>(null);
  const [limit, setLimit] = useState<number | null>(null);

  const reload = useCallback(() => {
    api
      .getSubscription()
      .then((s) => {
        setUsed(typeof s.generations_used === "number" ? s.generations_used : null);
        setLimit(typeof s.generations_limit === "number" ? s.generations_limit : null);
      })
      .catch(() => {
        setUsed(null);
        setLimit(null);
      });
  }, []);

  useEffect(reload, [reload]);
  return { used, limit, reload };
}

/** A readable message for a failed generate call. */
export function generationErrorMessage(err: unknown, fallback: string): string {
  if (isGenerationQuotaError(err)) {
    return "You've used every generation in this billing period. Upgrade in Settings › Billing, or wait for the reset.";
  }
  return err instanceof Error && err.message ? err.message : fallback;
}
