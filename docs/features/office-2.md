# Office 2 (plan, 2026-11-05)

Status: agreed with Moishe, building on `feature/office-2`. One branch, one push. Sources: Moishe's list and the meeting with Barry (5 Nov). Mostly the phone view; some of it on computer too. The WhatsApp chat is saved on `archive/whatsapp-chat`. Email chat research is on `feature/email-chat` and is not part of this.

## Home
- Phone: no greeting, no range bar (it stays on All). Also hide Gold applications, Waiting for you and Hot leads. Keep Leads, Recent activity and the rest.
- Three cards with two rings each:
  1. **Waiting for approval:** Gold and memberships, worded so it is clear they wait.
  2. **Approved:** Gold and memberships.
  3. **Revenue:** Gold and memberships, a 12-month estimate.
- Everything is tappable: Waiting rings open the approval lists, Approved rings open the approved lists on Registered and Gold, Revenue opens the Revenue page.
- Computer: the cards side by side.
- A small link to the Spa 99 website at the top of Home, not in the nav.

## Membership approval (Barry's view only)
- Approve moves to Approved, Decline moves to Declined. **The customer's membership and emails never change.**
- All existing registered people start unapproved, except Gold he approved. New registrations join as waiting.
- Registered page shows approved people, says how many are left to approve, and links to the approval list.
- Gold approval works as it does today.

## Phone tabs
Five, no More: Home, Approach list, Analytics, Leads, Revenue. Assistant hidden on phone only, stays on computer.

## Revenue page
Estimated annual. Gold = count x 199. Memberships = each member's actual price including a kept sale price. **All prices are excluding VAT.** Show ex and inc VAT, by plan and tier, monthly and yearly, members counted, average per member, and possible revenue from those waiting. Clearly labelled an estimate.

## VAT wording
Gold shows £199 + VAT wherever the Office shows it. Public site prices are not changed in this branch: UK rules generally require consumer prices to include VAT, so Moishe checks with his accountant first.

## Leads
- Shows everyone with no account and not on the Approach list. A "Has a number" filter.
- Top cards: Leads and Registered only, true totals, tappable. Hot leads goes.
- Added to the Approach list = gone from Leads. From the list he can go back to Leads or to Archive.
- Phone: scrolling loads more by itself with a loading animation until the end. Show More no longer hidden behind the nav. Applies to every long list.
- Whole rows tappable everywhere, with visible tap feedback.

## Approach list
- Registering removes him from Leads and the Approach list automatically (replaces the Registered tab there).
- Emailing one person keeps him on the list, tagged Emailed, with a filter.

## Registered list (computer and phone)
- Separate Membership and Gold tables, with filters.
- The Gold column shows only people who applied and are not yet approved. An approved Gold member does not show it.
- Every registered count is the true total, no "moved on from leads".

## WhatsApp
- Remove the WhatsApp tab, chat, templates, media, voice, Link it, push and PWA notifications from the Office. Installing the Office as an app stays.
- The WhatsApp button opens `wa.me` to that person. Mobile needed; otherwise the Details row to add one.
- Live chats: copy kept in the RDS snapshot, tables dropped (they hold foreign keys to users that would block deleting staff and members).
- 020 number: a small signed webhook answers anyone messaging it with one line pointing to the site's WhatsApp number. Stores nothing. Status webhook goes.
- System > Settings WhatsApp number must be the old number.

## Emails
- Every automatic email and group send can choose its sender: a dropdown of staff with a @spa99.uk address, default hello@. Select, not type.
- Group send to all leads, default wording from Barry, editable: asks them to join, which he personally approves for special discounts and prices, to WhatsApp him, and to give the number they have WhatsApp on. Includes an add-your-number link. Unsubscribe link stays.
- Leads stay in Leads after the send, tagged Emailed.
- **Add-your-number link:** a personal signed link to a small page with his email filled in. Saves the mobile, moves him to the Approach list. Refuses a taken number, tampered or expired link. No sign-in.

## Not doing
Bigger WhatsApp button on the website. A tag for people who registered without the questions. Business profile logo (Moishe, not code).
