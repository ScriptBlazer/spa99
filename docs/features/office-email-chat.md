# Email chat in the Office (plan, 2026-11-04)

Status: planned, building on `feature/whatsapp`. Decisions in PROJECT.md (2026-11-04 rows).

## Goal
Staff have two clearly separate ways to talk to a person: **WhatsApp** and **Email**. Email is a real chat: staff write in the Office, he replies from his normal mailbox, and the reply lands in the Office thread.

This reverses 2026-11-03 "email Message goes away, staff messages go by WhatsApp only". Automatic emails and Send guide are unchanged.

## How a reply gets back (Postmark inbound)
- Each thread has a random token. Office emails go from hello@ with `Reply-To: reply+<token>@<EMAIL_INBOUND_DOMAIN>`.
- Postmark receives mail for that domain and POSTs JSON to our inbound webhook. `MailboxHash` holds the token; `StrippedTextReply` holds only his new text (fall back to `TextBody`; if there is only `HtmlBody`, strip it to text). `MessageID` makes the webhook idempotent. Attachments arrive base64.
- Postmark retries on anything but 200, and stops on 403 (10 retries, up to 6 hours apart).
- `EMAIL_INBOUND_DOMAIN` blank: Reply-To stays hello@, the Office still sends and shows sent emails, and the screen says replies go to the hello@ mailbox.

## Setup Moishe does (no code)
1. Postmark plan must include inbound: 10K Pro ($16.50 a month) or Platform ($18), against Basic ($15), per Postmark's August 2025 update. Check Account > Plans & Add-ons.
2. Cloudflare DNS: `MX`, name `reply`, value `inbound.postmarkapp.com`, priority 10. This subdomain only, so hello@ and BML mail are untouched.
3. Postmark > server > Inbound stream > Settings: inbound domain `reply.spa99.uk`, webhook URL with its own password.
4. Server `.env`: `EMAIL_INBOUND_DOMAIN=reply.spa99.uk`, webhook user and password.

## Screens
- **Reach out card** (lead, person, Gold): two labelled parts, WhatsApp and Email, each with its own button and status. A channel that cannot be used stays visible and says why.
- **Email** in the Office navigation: inbox and thread, in the same family as WhatsApp but visibly a different channel.
- Thread: his and our emails, subject on the first and when it changes, attachments, delivery state, bounce shown plainly. Staff can write at any time (no 24-hour window).
- The assistant chat tab is renamed **Assistant** so "chats" no longer means three things.

## Rules
- Viewing: `reader`. Sending: `editor` (Approver or Admin and up), same as WhatsApp.
- Text only is rendered: no HTML from an email ever reaches the page. Attachments download, they never open inline, except images and PDFs.
- A Gold email sent from the application marks New as Contacted, once, like WhatsApp.
- Replies notify staff by the same push and mute setting as WhatsApp.
- Reply from another address (forwarded mail): stored, and the bubble shows that address.
- Spam flagged by Postmark (`X-Spam-Status: Yes`): stored and marked, no push.
- UK GDPR: threads, messages and files are in staff delete and export. Member self-service includes a thread only when his account's email is verified and equals the thread address.
