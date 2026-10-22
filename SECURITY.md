# Security and sensitive findings

StableGuard is research software. A positive legacy classification is not proof
of an exploitable vulnerability, and a negative or empty result is not assurance
that a contract is safe.

## Credentials and code disclosure

Keep real keys in a private `.env` file or protected environment variables. Do not
include them in issue reports, screenshots, commands, or committed configuration.
Scanning sends source excerpts and analysis context to the configured provider;
obtain permission before submitting private or third-party confidential code.

Build systems may execute code from the analyzed repository. Review untrusted
build configuration and use an isolated environment without unnecessary secrets.

## Reporting vulnerabilities

A verified maintainer contact and private reporting channel have not yet been
configured for this release. Do not invent a security email or publish credentials
or actionable details of an unpatched third-party vulnerability in a public issue.

The repository owner should configure a private reporting channel before public
release. For a finding in an analyzed protocol, follow that protocol's established
disclosure process and distinguish a tool-generated allegation from source-verified
evidence.

No supported-version schedule, response-time commitment, or production-security
guarantee is established by this draft policy.
