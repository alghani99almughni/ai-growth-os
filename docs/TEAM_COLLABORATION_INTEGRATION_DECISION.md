# Internal team collaboration integration decision

## Recommendation

Use **Mattermost as a separate internal collaboration service**, linked from the AI Growth OS Super Admin workspace. Keep customer-facing calls, tenant CRM conversations, and visitor/customer data inside AI Growth OS. Mattermost should serve platform staff and operations teams only.

## Why not host it inside the existing AI Growth OS Render web service?

Mattermost is a separate server application with a PostgreSQL database and persistent file storage. Mattermost's deployment documentation lists PostgreSQL 14+ as supported and recommends a pilot before scaling. Its self-hosted Calls feature requires HTTPS/WebSocket signaling plus direct TCP/UDP media ports (default 8443); those ports must reach the call media service directly rather than being proxied through a normal HTTPS reverse proxy.

Sources:
- Mattermost server requirements: https://docs.mattermost.com/deployment-guide/software-hardware-requirements
- Mattermost Calls deployment/network requirements: https://docs.mattermost.com/deployment-guide/calls/calls-deployment-guide

Because the current AI Growth OS deployment is a Render web/API stack and internal voice calls need dedicated media networking, deploying Mattermost as another process inside the current web service is not a safe or supportable design.

## Integration plan

1. Provision Mattermost Cloud for the fastest pilot, or a separate Linux VM/container host with PostgreSQL, persistent file/object storage, HTTPS, backups, and the required Calls ports if self-hosting is mandatory.
2. Add a Super Admin **Team Collaboration** navigation entry that opens the configured Mattermost workspace. Use a normal external link first; do not rely on iframe embedding because the provider may prohibit it.
3. Keep tenant users isolated from platform staff by default. No customer/tenant is automatically added to Mattermost.
4. Later, add SSO/identity mapping and selected event notifications (for example, deployment failures or platform incidents) only after workspace URL, identity provider, and access policy are approved.
5. Keep customer WebRTC, call recordings/transcripts, tenant support inboxes, and visitor records out of Mattermost unless a deliberate data-sharing policy is approved.

## Acceptance checklist

- [ ] Workspace URL and plan selected by the platform owner.
- [ ] Platform staff roles and onboarding/offboarding process defined.
- [ ] Two-user text chat tested.
- [ ] Audio call tested from desktop and mobile; verify network/media connectivity.
- [ ] File upload and retention/backup tested.
- [ ] AI Growth OS link works and does not grant tenant users unintended access.
- [ ] No production tenant data is copied into Mattermost by default.

## Decision still needed

Choose **Mattermost Cloud** for the lowest operations burden, or **self-hosted Mattermost** on a separate host for greater infrastructure control. Do not deploy a self-hosted instance on the existing AI Growth OS Render web service.
