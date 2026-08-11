# Account & Security

## Password Reset

Password resets are self-service via the "Forgot password" link on the login
page. Reset links expire after 20 minutes; a customer reporting an "expired
link" error just needs to request a new one, not a manual reset from support.

## Two-Factor Authentication

Two-factor authentication (2FA) can be enabled from **Account > Security**.
SMS and authenticator-app (TOTP) methods are both supported. Hardware
security keys (e.g. YubiKey) are **not** supported yet — this comes up
regularly enough that it's worth stating proactively rather than waiting for
the customer to discover it.

A customer locked out after losing their 2FA device must verify identity
through the account-recovery flow at acme.com/recover; support cannot disable
2FA directly over chat.

## Account Deletion

Account deletion requests are processed within 30 days of the request and are
irreversible after that window closes. Any active subscription must be
cancelled first — a deletion request does not automatically cancel billing.
