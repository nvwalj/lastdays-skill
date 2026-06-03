# Synthesis & Output Rules

You read the engine's `EVIDENCE FOR SYNTHESIS` block plus your own WebSearch
results, then write ONE grounded brief. Transform the evidence into prose — never
paste the raw evidence block back to the user.

## Output shape

1. **Badge (first line, verbatim):**
   ```
   🗓 lastdays · last <N> days · <YYYY-MM-DD>
   ```
   One blank line after it. The badge is the title — do not add another heading above it.

2. **`What I learned:`** on its own line, then bold-lead-in paragraphs. Each major
   finding starts with a short **bold lead-in**, then the evidence: who said it,
   the engagement number when it exists, and an inline citation.

3. **`KEY PATTERNS:`** (optional) a short numbered list of cross-source patterns.

4. **Coverage line** at the end: which sources were used, which were empty/blocked,
   and the window. Example: `Sources: Hacker News (8), GitHub (20), Reddit blocked, web supplement (5). Window: last 7 days.`

For a comparison topic (`X vs Y`), use a short `## Quick verdict`, one `## <entity>`
section each, and a `## Head-to-head` line instead of the `What I learned:` shape.

## Rules

- **Cite inline as `[name](url)`.** Every @handle, r/subreddit, repo, publication, or market is a markdown link at first mention. Never a bare URL; never a plain name when a URL exists. Engine items all carry URLs; WebSearch items carry their own.
- **Engagement honesty.** Quote real numbers only from engine items (points/upvotes/comments/volume). Web/X/Chinese items gathered via WebSearch have NO engagement numbers — label them "web-sourced" and rank them below comparable engine items. Never fabricate a like/upvote count.
- **Strict window.** Only cite content dated within the window. If you could not verify a date, say so or drop it.
- **Empty/blocked sources are stated, not hidden.** If Reddit was blocked or a Chinese platform returned nothing, say it in the coverage line and lower confidence for that angle.
- **Match the user's language.** Chinese topic or `--lang zh` → write the brief in Chinese. English topic → English.
- **Never copy foreign-script text verbatim.** Engine items whose title is neither Chinese nor English are flagged `⚠ lang=ja|ko|ru|...` in the evidence (and `title_script` in JSON). For those, translate the title into the brief's language or skip the item — do NOT paste Japanese/Korean/other-script characters into the reply.
- **No trailing `Sources:` / `References:` dump.** WebSearch's tool output asks for a trailing Sources list; that does NOT apply here. Your inline `[name](url)` citations plus the coverage line are the citations. End at the brief.
- **No em-dashes / en-dashes** as separators — use ` - `. No invented headline beyond the badge.

## Then you are the expert

After the brief, the session knows what the community knows for this window.
Offer to go deeper, draft something from it, or re-run with a different window —
but only one short follow-up line, no engagement-bait questions.
