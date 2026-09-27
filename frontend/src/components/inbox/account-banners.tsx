"use client";

import Link from "next/link";
import { Notice } from "@/components/ui/empty-state";
import { platformLabel } from "@/components/posts/platform";
import type { InboxAccount } from "@/lib/api-inbox";

function waitLabel(seconds: number | null): string {
  if (seconds == null) return "Try again in a few minutes.";
  if (seconds < 90) return `Try again in about ${Math.max(1, seconds)} seconds.`;
  return `Try again in about ${Math.ceil(seconds / 60)} minutes.`;
}

function accountName(a: InboxAccount): string {
  return a.handle ? `${platformLabel(a.platform)} (${a.handle})` : platformLabel(a.platform);
}

const ACCOUNTS_LINK = (
  <Link href="/setup/accounts" className="font-medium underline">
    Setup › Accounts
  </Link>
);

/**
 * One honest line per account that isn't simply "ok with items": why it has
 * nothing, in the platform's words where there are any, and what to do.
 */
export function AccountBanners({
  accounts,
  onRetry,
}: {
  accounts: InboxAccount[];
  onRetry: () => void;
}) {
  const anyConnected = accounts.some((a) => a.status !== "not_connected");
  const notices = accounts.flatMap((a) => {
    const key = `${a.platform}-${a.account_id ?? "none"}`;
    switch (a.status) {
      case "needs_reconnect":
        return [
          <Notice key={key} tone="warning" title={`Reconnect ${accountName(a)} to read its inbox`}>
            {a.message} Reconnect it in {ACCOUNTS_LINK}.
          </Notice>,
        ];
      case "api_access_denied":
        return [
          <Notice key={key} tone="warning" title={`${accountName(a)}: inbox access denied`}>
            {a.message}{" "}
            {a.platform === "linkedin"
              ? "Once the LinkedIn app is approved for it, reconnect in "
              : "If your API access changed, reconnect in "}
            {ACCOUNTS_LINK} to grant it.
          </Notice>,
        ];
      case "rate_limited":
        return [
          <Notice key={key} tone="info" title={`${accountName(a)} is rate limited`}>
            {a.message} {waitLabel(a.retry_after)}
          </Notice>,
        ];
      case "error":
        return [
          <Notice key={key} tone="danger" title={`Couldn't load ${accountName(a)}`}>
            {a.message}{" "}
            <button type="button" onClick={onRetry} className="font-medium underline">
              Try again
            </button>
          </Notice>,
        ];
      case "unsupported":
        return [
          <Notice key={key} tone="info">
            {a.message}
          </Notice>,
        ];
      case "not_connected":
        // With nothing connected at all, the list's empty state says it once.
        return anyConnected
          ? [
              <Notice key={key} tone="info">
                No {platformLabel(a.platform)} account is connected for this client. Connect one in {ACCOUNTS_LINK}{" "}
                to see its {a.platform === "twitter" ? "mentions" : "comments"} here.
              </Notice>,
            ]
          : [];
      case "ok":
        return a.message
          ? [
              <Notice key={key} tone="info">
                {accountName(a)}: {a.message}
              </Notice>,
            ]
          : [];
      default:
        return [];
    }
  });
  if (notices.length === 0) return null;
  return <div className="mb-4 space-y-2">{notices}</div>;
}
