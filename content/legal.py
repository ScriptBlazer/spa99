"""Starting text of the Privacy notice and the Terms of use (updated 2026-10-26). Sources for every statement and the open
proposals are in docs/features/legal.md. Written into content rows by `seed_phase1` (new installs) and
`backfill_site_data` (existing ones); after that the rows are edited in Control, never here.

How a legal body is written (one line per block, rendered by `content.legal_render`):
- a plain line is a paragraph
- "### Title {#id}" gives a small heading an anchor (lowercase letters, digits and dashes), e.g. /privacy/#chat
- "- " starts a list item (lines in a row make one list)
- "### " starts a small heading inside a part
- [words](/path/) or [words](https://...) is a link
- {contact} is the site's contact email (Site settings), as a link
- {ico} and {hosting} are filled from the `ico` and `hosting` rows of the privacy page. While a row is empty, dev shows
  a marked placeholder; live drops "({token})" from the line, or the whole line when the token stands alone
- {gold_invite_days} is how long a Gold invite link works, in words (System > Defaults); {version} is the privacy version in Site settings; {opening} is the opening time, as everywhere else

Keys: `body` (title and intro), `updated` (the date shown), `part_N` (the numbered parts, in order), `contact`."""

UPDATED = "26 October 2026"
PRIVACY_UPDATED = "30 October 2026"  # invitation emails track opens; earlier: Ask us chat (Anthropic) added, Postmark added as the email sender
INVITE_OPEN_LINE = ("- Invitation emails contain a tiny image (a tracking pixel), so we know whether the email was opened. "
                    "Other emails we send you do not.")
PRIVACY_VERSION = "2026-10-26"  # SiteSettings.privacy_version; recorded on everyone who accepts this notice

COMPANY_LINE = ("Spa 99 is run by BML SPA 99 LIMITED, a company registered in England (company number 16930909). "
                "Our registered office is 40 Wellington Avenue, London N15 6AS.")
POSTAL = "BML SPA 99 LIMITED, 40 Wellington Avenue, London N15 6AS"

PRIVACY_PARTS = [
    ("part_1", "Who we are", "\n".join([
        COMPANY_LINE,
        "The spa is at BML House, 99c Vale Road, London N4 1PR. We are part of BML Group.",
        "We are the data controller for the information in this notice. That means we decide how it is used, and we "
        "are responsible for looking after it.",
        "We are registered with the Information Commissioner's Office. Our registration number is {ico}.",
        "If you have a question about your information, write to {contact}.",
    ])),
    ("part_2", "What we collect", "\n".join([
        "We collect only what we need, and only when you do something on the site.",
        "### When you browse",
        "- Nothing that identifies you. We count visits without cookies (see Cookies, below).",
        "- If a page breaks, an error report is made. It leaves out names, email addresses and IP addresses, but can "
        "include your account's internal number and the type of browser.",
        "### When you take the guided journey",
        "- Your answers: when you would come, how often, what you would use, whether you come alone, what you do (and, "
        "for property, your link to property and roughly how many properties), how you heard about us, and anything "
        "you type in the short text boxes.",
        "- The membership we suggest, and why.",
        "- About the visit: the page that linked to us (if any), campaign tags in the link, the kind of device (phone, "
        "tablet or computer), and when you started and finished.",
        "Answers are saved as you go, even if you stop part way. They carry no name unless you register.",
        "- Your email address, if you give it. Before the journey shows your suggested membership and price, it asks for "
        "your email, with a tick to say Spa 99 may email you about opening. We keep the address with your answers, the "
        "date you gave it and the version of this notice in force. If you are signed in, we use your account email "
        "instead and do not ask.",
        "### When you register",
        "- Your name, email address, UK mobile number, date of birth and password. The password is stored scrambled "
        "(hashed), so nobody can read it, including us.",
        "- That you accepted the men-only policy and this notice (which version), with the dates.",
        "- Whether you would like news from us by email, and when you told us.",
        "- The membership you registered for, your account ID, and whether you have confirmed your email.",
        "- Sign-in records: when you sign in and out, failed attempts, and the IP address and browser used.",
        "### When you apply for the Gold Card",
        "- Your name, email address and mobile number.",
        "- What you do. For property: your link to property and roughly how many properties. Also the area you are "
        "based in, your company and role, whether you work with BML, who referred you, and any note you add.",
        "- Your journey answers, if you took the journey.",
        "- A potential rating (High, Medium or Low) worked out from your answers, with its reasons.",
        "- Whether you would like news from us by email, and which version of this notice you accepted.",
        "- Our decision and, if we approve, the date and the invitation we send you.",
        "- If our team writes to you about your application (for example to ask a question), a record of that email.",
        "### When you use the Ask us chat {#chat}",
        "- What you type to the assistant and its replies, with the time. If you gave your email to see prices, or you are "
        "signed in, the chat is linked to it. We do not store your IP address with a chat.",
        "### Change history",
        "- Earlier versions of your details (a change history): when your account, registration or Gold Card "
        "application changes, we keep the previous version, so we can see what changed and put mistakes right. "
        "Passwords are never kept in it.",
        "### Emails",
        "- A record of each email we send you: which email, when, and whether it went out.",
        INVITE_OPEN_LINE,
        "- Emails you send us, kept in our mailbox.",
        "### Our team",
        "- When our team use our own tools, we record what they do, with their IP address and browser, to keep the "
        "system secure. This covers team accounts only.",
    ])),
    ("part_3", "Why we use it", "\n".join([
        "The law asks us to name a lawful basis for each use. Here they are.",
        "### To run your account and registration",
        "Creating your account, keeping your registered membership, confirming your email, resetting your password and "
        "writing to you about opening. Basis: a contract with you, or steps you asked us to take before one.",
        "### To check you can join",
        "Spa 99 is for men aged 18 and over. We use your date of birth and your acceptance of the men-only policy to "
        "check this. Basis: steps before a contract, and our legitimate interest in running the spa as described.",
        "### To suggest a membership and plan the spa",
        "Your journey answers give you a suggestion. Added together with everyone else's, they show us which times and "
        "rooms matter most. Those figures are totals, never decisions about you. Basis: legitimate interests.",
        "### To consider a Gold Card application",
        "We read your application, and the potential rating helps us. Our team may email you with questions about it. The rating never decides on its own: a person "
        "does. Basis: steps before a contract, and legitimate interests.",
        "### To send news, only if you ask",
        "We send news by email only if you said yes. You can stop it at any time in My Spa 99, or by writing to "
        "{contact}. Basis: your consent.",
        "### To email you about opening after the journey",
        "If you gave your email in the guided journey and ticked the box, we use it to send news about the opening and "
        "to understand which membership suits people (your answers, linked to your address, show us what people "
        "choose). Basis: your consent. You can withdraw it at any time by following the unsubscribe link in any email "
        "or by writing to {contact}; we then stop emailing you and delete the address.",
        "### To answer your questions in the chat",
        "The Ask us assistant answers questions about Spa 99 from our own information. It does not make decisions about "
        "you. Basis: legitimate interests.",
        "### To keep the site and your account safe",
        "Sign-in records, limits on repeated attempts, error reports and our team's activity records. Basis: "
        "legitimate interests.",
        "### When the law requires it",
        "Keeping records we must keep, and answering lawful requests. Basis: legal obligation.",
        "### If you do not give us your details",
        "The guided journey is optional. To register or apply for the Gold Card, we need the details the form asks "
        "for; without them we cannot create your account or consider your application. News by email is always "
        "optional.",
        "We do not sell your information, and we do not use it for advertising.",
    ])),
    ("part_4", "Men only, 18 and over", "\n".join([
        "We ask for your date of birth to confirm you are 18 or over, and we ask you to accept our men-only policy. "
        "We use your date of birth for this and to run your membership, nothing else. We do not ask for documents online.",
        "The site is not meant for anyone under 18. If we learn that someone under 18 has an account, we delete it.",
    ])),
    ("part_5", "Cookies", "\n".join([
        "We use only cookies the site needs to work. No analytics, advertising or tracking cookies. That is why there "
        "is no cookie banner.",
        "- csrftoken: protects our forms from misuse. Lasts one year.",
        "- sessionid: keeps you signed in, or remembers a step while you use the site. Lasts up to two weeks. Our team's "
        "sign-ins to our own tools last up to 30 days.",
        "- messages: shows a short note, such as \"Saved\", on the next page. Gone when you close the browser.",
        "- spa99_journey: remembers your place in the guided journey, so you can come back to it. Lasts one year, and is "
        "removed when you sign out.",
        "While you fill in the Gold Card application, your browser keeps what you have typed in that tab, so a refresh "
        "does not lose it. The virtual tour also remembers a few display choices in that tab, such as the simpler view. "
        "Both stay on your device and are cleared when you close the tab.",
        "### The visitor counter",
        "To know how many people visit, we count without cookies. For each visit, our server mixes your IP address and "
        "browser details with a random value that changes every day, and turns them into a one-way code. The code lets "
        "us count you once a day. Your IP address and browser details are never stored. Each day's codes and random "
        "value are deleted the next day, so they cannot be traced back to you.",
        "We also note the name of the website that sent you, such as a search engine. Only the name, never the full "
        "address.",
    ])),
    ("part_6", "Who we share it with", "\n".join([
        "Only with companies that help us run the site. They work under contract, on our instructions, and may not use "
        "your information for anything else.",
        "- Website hosting ({hosting}): the servers and database the site runs on.",
        "- Amazon Web Services: stores the site's files and images (Amazon S3).",
        "- Postmark (ActiveCampaign): sends our emails, such as confirming your email, password resets and Gold Card "
        "updates. It handles your name, email address and the email itself.",
        "- Sentry: receives error reports when something breaks. Reports leave out names, email addresses and IP "
        "addresses, but can include your account's internal number and the type of browser.",
        "- Microsoft 365: our mailbox, where emails you send us are kept.",
        "- Anthropic: provides the AI assistant in the Ask us chat. It receives what you type in the chat, with our own "
        "information about the spa, so it can answer. It does not receive your name or email address.",
        "Gold Card applications are emailed to the people who decide on them for us. They may work for BML Group. "
        "Applications are not shared more widely.",
        "We may also share information when the law requires it, or to protect someone's safety. If the business is "
        "ever sold or reorganised, your information may pass to the new owner, who must respect this notice.",
    ])),
    ("part_7", "Where it is kept", "\n".join([
        "Our Amazon services run in London. Sentry keeps error reports in the European Union, which UK law recognises "
        "as protecting personal data properly.",
        "Postmark is based in the United States, so the emails we send you pass through and are briefly stored there. "
        "This is covered by the UK-US data bridge or the UK International Data Transfer Agreement.",
        "Anthropic, which runs the Ask us assistant, is based in the United States, so what you type in the chat is "
        "processed there. This is covered by the UK-US data bridge or the UK International Data Transfer Agreement. "
        "Please do not put personal or sensitive details in the chat.",
        "If a provider handles information outside the UK, for example for support, we make sure the safeguards UK law "
        "requires are in place, such as the UK International Data Transfer Agreement or the UK-US data bridge.",
    ])),
    ("part_8", "How long we keep it", "\n".join([
        "No longer than we need to.",
        "- Your account: while you keep it. You can delete it at any time. If an account is not used for three years, we "
        "write to you, then delete it.",
        "- Accounts whose email is never confirmed: 90 days.",
        "- Journey answers with no account: two years, then deleted.",
        "- Your email address from the journey: two years after you gave it, or until you unsubscribe, withdraw "
        "consent or register (then it is kept as part of your account), whichever comes first. The answers then stay "
        "only as anonymous figures.",
        "- Gold Card applications we do not approve: one year after our decision.",
        "- Sign-in records: one year.",
        "- Records of emails we send: two years.",
        "- Emails you send us: two years after we last hear from you.",
        "- Visitor counter codes: deleted the next day.",
        "- Ask us chats: 90 days, then deleted automatically.",
        "- Error reports: 90 days.",
        "- Change history: two years, or until you delete your account, whichever comes first.",
        "- Our team's activity records: two years.",
        "- Backups: replaced within 35 days.",
        "Where the law asks us to keep something longer, such as payment records once memberships begin, we keep it for "
        "the time the law requires.",
    ])),
    ("part_9", "Your rights", "\n".join([
        "You can ask us to:",
        "- show you the information we hold about you (access)",
        "- correct anything that is wrong (rectification)",
        "- delete your information (erasure)",
        "- hold your information but stop using it for a while (restriction)",
        "- stop using it where we rely on legitimate interests, and always for news (objection)",
        "- give it to you in a file you can take elsewhere (portability)",
        "Where we rely on your consent, you can withdraw it at any time.",
        "### Do it yourself in My Spa 99",
        "Under You, Download my data gives you a file of everything we hold about your account. Delete my account erases "
        "your account, your registration, any Gold Card applications made with your email, the email you gave in the journey, our records of "
        "emails about you, your sign-in records, and the change history of all of these. Your journey answers stay only as anonymous figures, no longer linked to you.",
        "For anything else, write to {contact}. We reply within one month, and there is no charge.",
    ])),
    ("part_10", "Complaints", "\n".join([
        "If you are unhappy with how we use your information, please tell us first at {contact}, so we can put it right.",
        "You can also complain to the Information Commissioner's Office at "
        "[ico.org.uk/make-a-complaint](https://ico.org.uk/make-a-complaint/) or on 0303 123 1113.",
    ])),
    ("part_11", "Changes to this notice", "\n".join([
        "We update this notice when what we do changes. The date at the top shows the current version. If a change "
        "matters to you, we will tell you by email.",
    ])),
]

TERMS_PARTS = [
    ("part_1", "About us", "\n".join([
        COMPANY_LINE,
        "Spa 99 is a private spa for men at BML House, 99c Vale Road, London N4 1PR, opening {opening}. We are part of BML Group.",
        "These terms cover your use of the Spa 99 website and your account. By using the site, you accept them.",
    ])),
    ("part_2", "Men only, 18 and over", "\n".join([
        "Anyone may read the site. Accounts, registration and the Gold Card are for men aged 18 and over.",
        "Spa 99 is a men-only spa. When you create an account, you confirm that you are a man aged 18 or over and that "
        "you accept this policy.",
    ])),
    ("part_3", "Your account", "\n".join([
        "- Give us accurate details, and keep them up to date.",
        "- Keep your password to yourself. If you think someone else has used your account, tell us straight away.",
        "- One account per person. Accounts are personal and cannot be passed on.",
        "- We may suspend or close an account that breaks these terms or is misused. Where we can, we will tell you why.",
        "- You can delete your account at any time in My Spa 99.",
    ])),
    ("part_4", "Registering is not a membership", "\n".join([
        "Registering tells us which membership interests you. It is not a contract for membership and does not hold a "
        "place. We take no payment now and ask for no card details.",
        "Plans, prices, hours and opening details on the site may change before we open.",
    ])),
    ("part_5", "Membership terms", "\n".join([
        "Before you pay for anything, we will give you the membership terms: prices, billing, how to cancel, and the "
        "house rules. They will be a separate agreement between you and us, which you accept at that point. Where they "
        "differ from the website, the membership terms apply.",
    ])),
    ("part_6", "The Gold Card", "\n".join([
        "The Gold Card is by application. We decide on each application at our discretion, and we may not give reasons.",
        "Applying does not create an account. If we approve, we email you a personal link to set one up. The link works "
        "once and expires after {gold_invite_days}; we can send a new one. Please do not share it.",
    ])),
    ("part_7", "Images and the virtual tour", "\n".join([
        "The spa is not open yet. Images and the virtual tour show how we intend it to look. They are illustrative, and "
        "the finished spa may differ in detail.",
    ])),
    ("part_8", "Our content", "\n".join([
        "The Spa 99 name, the swan mark, this website and its content belong to us or to those who let us use them.",
        "You may view and share pages for your own use. Please do not copy, change or use them commercially without our "
        "written permission.",
    ])),
    ("part_9", "Using the site fairly", "\n".join([
        "Please do not:",
        "- break the law, or help anyone else to",
        "- try to reach accounts or areas that are not yours",
        "- disrupt the site, overload it, copy it automatically, or test its security without our permission",
        "- give false details or pretend to be someone else",
        "- send anything harmful, such as viruses",
    ])),
    ("part_10", "Our responsibility to you", "\n".join([
        "We work to keep the site accurate and available, but we cannot promise it will always be uninterrupted or free "
        "of errors. We may change or pause parts of it.",
        "We are responsible for loss you suffer that is a foreseeable result of our breaking these terms or failing to "
        "use reasonable care. We are not responsible for loss that was not foreseeable, or for business losses: the site "
        "is for personal use.",
        "Links to other websites are for convenience. We are not responsible for their content.",
        "Nothing in these terms limits our liability for death or personal injury caused by negligence, for fraud, or "
        "for anything else the law does not allow us to limit. Your legal rights as a consumer are not affected.",
    ])),
    ("part_11", "Your privacy", "\n".join([
        "How we use your information is explained in our [privacy notice](/privacy/).",
    ])),
    ("part_12", "Changes to these terms", "\n".join([
        "We may update these terms. The date at the top shows the current version. If a change affects your account in "
        "a way that matters, we will tell you by email.",
    ])),
    ("part_13", "Law", "\n".join([
        "These terms are governed by the law of England and Wales, and the courts of England and Wales may hear any "
        "dispute. If you live in Scotland or Northern Ireland, you may also bring a claim in your local courts.",
    ])),
]

# (section key, heading, body, cta label, cta url) as in content.seed.PAGES
PRIVACY = ("Privacy notice", "What Spa 99 collects, why, and the choices you have.", [
    ("body", "Privacy notice.", "What we collect when you use the Spa 99 website, why, and the choices you have. "
     "Plain words, nothing hidden.", "", ""),
    ("updated", "Last updated", PRIVACY_UPDATED, "", ""),
    ("ico", "ICO registration number", "ZC284282", "", ""),  # BML Spa 99 Limited, registered 2026-10-26
    ("hosting", "Hosting provider name", "Amazon Web Services, London region", "", ""),  # chosen 2026-10-26
    *[(key, heading, body, "", "") for key, heading, body in PRIVACY_PARTS],
    ("contact", "Contact", "Write to {contact}, or by post to " + POSTAL + ".", "", ""),
])

TERMS = ("Terms of use", "The terms for using the Spa 99 website and your account.", [
    ("body", "Terms of use.", "The terms for using the Spa 99 website and your account. Please read them with our "
     "[privacy notice](/privacy/).", "", ""),
    ("updated", "Last updated", UPDATED, "", ""),
    *[(key, heading, body, "", "") for key, heading, body in TERMS_PARTS],
    ("contact", "Contact", "Write to {contact}, or by post to " + POSTAL + ".", "", ""),
])

# The placeholder rows seeded before 2026-10-23: replaced only while they still have exactly this wording.
OLD_PLACEHOLDER_BODY = "To be supplied."
OLD_DRAFT_NOTE = "The full text is to be supplied before launch."
OLD_CONTACT_BODY = "Write to us at"
OLD_PAGE_TEXT = {  # page key -> {field: (old, new)}
    "privacy": {"meta_description": ("How Spa 99 uses your information.", PRIVACY[1])},
    "terms": {"title": ("Terms", TERMS[0]), "meta_description": ("Spa 99 terms.", TERMS[1])},
}
OLD_BODY_HEADINGS = {"privacy": "Privacy notice.", "terms": "Terms."}

# Bodies as first written on 2026-10-23 (round 1). backfill_site_data replaces a row only while it is exactly this.
ROUND_1_PRIVACY_BODIES = {
    'part_2': 'We collect only what we need, and only when you do something on the site.\n### When you browse\n- Nothing that identifies you. We count visits without cookies (see Cookies, below).\n- If a page breaks, an error report is made. It is set up to leave out personal details.\n### When you take the guided journey\n- Your answers: when you would come, how often, what you would use, whether you come alone, what you do (and, for property, your link to property and roughly how many properties), how you heard about us, and anything you type in the short text boxes.\n- The membership we suggest, and why.\n- About the visit: the page that linked to us (if any), campaign tags in the link, the kind of device (phone, tablet or computer), and when you started and finished.\nAnswers are saved as you go, even if you stop part way. They carry no name unless you register.\n### When you register\n- Your name, email address, UK mobile number, date of birth and password. The password is stored scrambled (hashed), so nobody can read it, including us.\n- That you accepted the men-only policy and this notice (which version), with the dates.\n- Whether you would like news from us by email, and when you told us.\n- The membership you registered for, your account ID, and whether you have confirmed your email.\n- Sign-in records: when you sign in and out, failed attempts, and the IP address and browser used.\n### When you apply for the Gold Card\n- Your name, email address and mobile number.\n- What you do. For property: your link to property and roughly how many properties. Also the area you are based in, your company and role, whether you work with BML, who referred you, and any note you add.\n- Your journey answers, if you took the journey.\n- A potential rating (High, Medium or Low) worked out from your answers, with its reasons.\n- Our decision and, if we approve, the date and the invitation we send you.\n### Emails\n- A record of each email we send you: which email, when, and whether it went out.\n- Emails you send us, kept in our mailbox.\n### Our team\n- When our team use our own tools, we record what they do, with their IP address and browser, to keep the system secure. This covers team accounts only.',
    'part_3': "The law asks us to name a lawful basis for each use. Here they are.\n### To run your account and registration\nCreating your account, keeping your registered membership, confirming your email, resetting your password and writing to you about opening. Basis: a contract with you, or steps you asked us to take before one.\n### To check you can join\nSpa 99 is for men aged 18 and over. We use your date of birth and your acceptance of the men-only policy to check this. Basis: steps before a contract, and our legitimate interest in running the spa as described.\n### To suggest a membership and plan the spa\nYour journey answers give you a suggestion. Added together with everyone else's, they show us which times and rooms matter most. Those figures are totals, never decisions about you. Basis: legitimate interests.\n### To consider a Gold Card application\nWe read your application, and the potential rating helps us. The rating never decides on its own: a person does. Basis: steps before a contract, and legitimate interests.\n### To send news, only if you ask\nWe send news by email only if you said yes. You can stop it at any time in My Spa 99, or by writing to {contact}. Basis: your consent.\n### To keep the site and your account safe\nSign-in records, limits on repeated attempts, error reports and our team's activity records. Basis: legitimate interests.\n### When the law requires it\nKeeping records we must keep, and answering lawful requests. Basis: legal obligation.\nWe do not sell your information, and we do not use it for advertising.",
    'part_5': 'We use only cookies the site needs to work. No analytics, advertising or tracking cookies. That is why there is no cookie banner.\n- csrftoken: protects our forms from misuse. Lasts one year.\n- sessionid: keeps you signed in, or remembers a step while you use the site. Lasts up to two weeks.\n- messages: shows a short note, such as "Saved", on the next page. Gone when you close the browser.\n- spa99_journey: remembers your place in the guided journey, so you can come back to it. Lasts one year, and is removed when you sign out.\nWhile you fill in the Gold Card application, your browser keeps what you have typed in that tab, so a refresh does not lose it. It stays on your device, and is cleared when you close the tab.\n### The visitor counter\nTo know how many people visit, we count without cookies. For each visit, our server mixes your IP address and browser details with a random value that changes every day, and turns them into a one-way code. The code lets us count you once a day. Your IP address and browser details are never stored. Each day\'s codes and random value are deleted the next day, so they cannot be traced back to you.\nWe also note the name of the website that sent you, such as a search engine. Only the name, never the full address.',
    'part_6': "Only with companies that help us run the site. They work under contract, on our instructions, and may not use your information for anything else.\n- Website hosting ({hosting}): the servers and database the site runs on.\n- Amazon Web Services: stores the site's files and images (Amazon S3) and sends our emails (Amazon SES).\n- Sentry: receives error reports when something breaks. Reports are set up to leave out personal details.\n- Microsoft 365: our mailbox, where emails you send us are kept.\nGold Card applications are emailed to the people who decide on them for us. They may work for BML Group. Applications are not shared more widely.\nWe may also share information when the law requires it, or to protect someone's safety. If the business is ever sold or reorganised, your information may pass to the new owner, who must respect this notice.",
    'part_8': "No longer than we need to.\n- Your account: while you keep it. You can delete it at any time. If an account is not used for three years, we write to you, then delete it.\n- Accounts whose email is never confirmed: 90 days.\n- Journey answers with no account: two years, then deleted.\n- Gold Card applications we do not approve: one year after our decision.\n- Sign-in records: one year.\n- Records of emails we send: two years.\n- Emails you send us: two years after we last hear from you.\n- Visitor counter codes: deleted the next day.\n- Error reports: 90 days.\n- Our team's activity records: two years.\n- Backups: replaced within 35 days.\nWhere the law asks us to keep something longer, such as payment records once memberships begin, we keep it for the time the law requires.",
    'part_9': 'You can ask us to:\n- show you the information we hold about you (access)\n- correct anything that is wrong (rectification)\n- delete your information (erasure)\n- hold your information but stop using it for a while (restriction)\n- stop using it where we rely on legitimate interests, and always for news (objection)\n- give it to you in a file you can take elsewhere (portability)\nWhere we rely on your consent, you can withdraw it at any time.\n### Do it yourself in My Spa 99\nUnder You, Download my data gives you a file of everything we hold about your account. Delete my account erases your account, your registration, any Gold Card applications made with your email, our records of emails about you, and your sign-in records. Your journey answers stay only as anonymous figures, no longer linked to you.\nFor anything else, write to {contact}. We reply within one month, and there is no charge.',
}
