/** @type {import('next').NextConfig} */
const nextConfig = {
  // No `typescript.ignoreBuildErrors` / `eslint.ignoreDuringBuilds` here on purpose:
  // with those set, `next build` type-checks nothing and lints nothing, so a production
  // build cannot fail on a type error. Do not reintroduce them to unblock a deploy —
  // fix the error instead.
};

export default nextConfig;
