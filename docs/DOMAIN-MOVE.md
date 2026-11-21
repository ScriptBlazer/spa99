# Move to spa99.co.uk (website, Office, System, Control)

Decided 2026-11-20 (PROJECT.md). Do it at a quiet time: between steps 3 and 5 the old .uk addresses are down for a few minutes.

## What needs no code change
- The site, Office, System and Control read their address from the server `.env`. Caddy uses the same values, so it gets the new certificates by itself.
- Allowed hosts follow the four domains automatically.
- SEO tags follow the address the page is on: the canonical link, `robots.txt` and `sitemap.xml` all switch to .co.uk by themselves.

## Steps

**1. Cloudflare, spa99.co.uk zone**
- Delete the rule that redirects .co.uk to .uk.
- SSL/TLS mode is Full on both zones, which is fine.
- DNS, all grey (DNS only), the same as .uk today. Caddy holds the certificates.
  - Point the apex A record at the server, 3.8.30.182.
  - Delete the second GoDaddy A record.
  - Set `www` (CNAME spa99.co.uk) to DNS only.
  - Add A records for `office`, `system` and `control`, all 3.8.30.182.

**2. Server `.env`** (in `~/spa99`). Change these:
- `DOMAIN=spa99.co.uk`
- `OFFICE_DOMAIN=office.spa99.co.uk`
- `SYSTEM_DOMAIN=system.spa99.co.uk`
- `CONTROL_DOMAIN=control.spa99.co.uk`
- `DEFAULT_FROM_EMAIL=Spa 99 <hello@spa99.co.uk>`, if it isn't already.
- `SITE_URL`, `OFFICE_URL`, `SYSTEM_URL`, `CONTROL_URL` and `EMAIL_SENDING_DOMAIN`: only if they are filled in. Blank is fine.

**3. Restart:** `docker compose up -d`, then `docker compose logs -f caddy`.
- Wait for "certificate obtained" for all five names.
- Open all four sites on .co.uk and sign in.

**4. (none)** The .co.uk records stay grey, as .uk was.

**5. Cloudflare, spa99.uk zone:** add one Redirect Rule that covers every address.
- Rule type: Wildcard pattern.
- Request URL: `http*://*spa99.uk/*` (covers http too, so http goes to .co.uk in one 301; changed 2026-11-21 for Google's Change of address check)
- Target URL: `https://${2}spa99.co.uk/${3}`
- Status code: 301. Tick "Preserve query string".
- Create the rule ahead of time: it does nothing while the .uk records are grey. At the switch, turn the .uk A records (`@`, `office`, `system`, `control`) and `www` orange (proxied), or the redirect never runs.
- Don't touch the MX or email records: .uk email keeps working.

**6. Twilio:** no change. Moishe decided (2026-11-21) the Spa 99 number stays on Sam's function. Office gets calls and voicemails through the read-only Twilio import, which doesn't use the domain.

**7. Postmark:** done 2026-11-21. The bounce/spam webhook now points at spa99.co.uk (same login), and Postmark shows it Verified. The inbound webhook is empty, so it was left alone.

**8. Amazon SES / SNS:** nothing to change. SES isn't in use (we send through Postmark). GO-LIVE.md now has the .co.uk address for when we move to SES.

**9. Google:**
- Search Console:
  - add `spa99.co.uk` as a Domain property (verify with the TXT record in Cloudflare);
  - submit `https://spa99.co.uk/sitemap.xml`;
  - then, in the old spa99.uk property, use Settings > Change of address > spa99.co.uk.
  - Status 2026-11-21: both verified, sitemap sent. Change of address still says "couldn't fetch http://spa99.uk/" although the redirect is right and Google's live test passes. Recrawl requested; retry in a day or two (optional).
- Analytics: none. The site has no Google Analytics; visitor figures are our own (Office > Analytics) and need no change.
- Google Business Profile, Instagram and other bios: update the website link.
- Keep the .uk redirect for good, at least a year. Search ranking moves over with the 301s.

**Still to do (after Shabbos):** one test email from Office, to check Postmark on spa99.co.uk.

**10. Check:**
- `https://spa99.uk/some/page?x=1` lands on the same page on .co.uk, and the same for office, system and control.
- `/health/` works on .co.uk.
- One test email from Office goes out from @spa99.co.uk.
- In System, every staff sender address is @spa99.co.uk. An old @spa99.uk one fails the sending-domain check.
