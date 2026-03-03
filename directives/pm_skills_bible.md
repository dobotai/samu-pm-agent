# PM Agent Skills Bible

> This document defines the context, decision frameworks, and response patterns for an AI agent assisting with Project Management at KS Media. Use this to understand what responses are valuable vs. noise.
>
> **Full SOP reference:** `directives/ops_manager_sop.md` — 14-part canonical SOP for all PM operations.
> When in doubt about workflows, status meanings, or edge cases, consult that document.

---

## 1. Understanding the Business

### What KS Media Does
- Video production agency creating YouTube content for B2B SaaS clients
- Monthly video packages (typically 4 videos/month per client)
- Full service: scripting, editing, thumbnails, scheduling, publishing

### The PM's Core Mission
**Keep videos moving through the pipeline on time while maintaining quality.**

The PM is the operational hub - the person who ensures nothing falls through the cracks between clients, editors, and leadership (Samu).

### Key Stakeholders
| Role | What They Need | Communication Style |
|------|---------------|---------------------|
| **Samu** (Owner) | Updates on everything, strategic decisions, client comms approval | Over-communicate. No surprises. |
| **Editors** | Clear assignments, timely feedback, payment info | Direct, supportive, deadline-focused |
| **Clients** | Videos delivered on time, quick responses | Professional, careful (get approval before responding) |

---

## 2. The Video Lifecycle

Understanding where a video is determines what action is needed.

### Status Flow
```
30 - Script Sent to Client
    ↓
39 - Client Making fixes (client recording/fixing)
    ↓
41 - Sent to Editor (assigned, waiting for editor to start)
    ↓
50 - Editor Confirmed (editor accepted, actively working)
    ↓
59 - Editor Revisions (editor implementing QC/client revisions)
    ↓
60 - Submitted for QC (PM needs to review)
    ↓
75 - Sent to Client For Review (waiting on client feedback)
    ↓
80 - Approved By Client (ready to schedule)
    ↓
100 - Scheduled - DONE
```

### What Each Status Means for PM Action

| Status | PM Action Required | Urgency |
|--------|-------------------|---------|
| **60 - QC** | Review video NOW. This is priority #1. | HIGH |
| **80 - Approved** | Schedule on YouTube immediately | HIGH |
| **59 - Revisions** | Follow up with editor on progress | MEDIUM |
| **75 - Sent to Client** | Monitor for client response, follow up if needed | MEDIUM |
| **50 - Editor Confirmed** | Check if deadline approaching, proactive check-in | LOW-MEDIUM |
| **41 - Sent to Editor** | Wait, but follow up if no confirmation | LOW |

### Status Reality (from operations experience)

**Most-used statuses in practice:** 41, 59, 60, 75
Many statuses (30, 39, 50) get skipped frequently. Videos often jump directly between key stages.

**Status 60 has two Airtable variants:**
- "60 - Submitted for QC"
- "60 - Internal Review"
Both mean the same thing: PM needs to review. Scripts must match BOTH.

**Slack automation triggers:**
- **41 - Sent to Editor** → editor gets pinged in their channel
- **59 - Editing Revisions** → editor gets pinged that there are revisions
- **60 - Submitted for QC** → PM gets pinged for review
- **75 - Sent to Client For Review** → editor gets notified video is with client

**Deadline clarification:**
- Deadline = **V1 delivery** (first draft), NOT final delivery
- Set 3 days from "Sent to Editor" assignment
- A video past deadline but in revision cycles (59) is **normal**
- A video past deadline still at 41/50 is **concerning**
- Simon updates deadlines ~weekly; many are stale — context matters

**Skipped statuses:**
- Status 50 (Editor Confirmed) often skipped — editors go directly from 41 to 60
- Status 39 (Client Making Fixes) rarely used
- "Client Sent Revisions" — always bypassed in current practice. Simon sets directly to 59 (Editing Revisions) for both QC revisions and client revisions
- "Approved by Agency" — skipped. Simon goes directly from 60 (QC) to 75 (Sent to Client). This status is not tracked by any agent scripts and should not appear in normal operations

**Common flow in practice:**
41 → 60 → 59 → 60 → 75 → 59 → 60 → 75 → 80 → 100
Videos can bounce between QC (60) and revisions (59) multiple times before going to client (75), and between client review (75) and revisions (59) after client feedback.

### QC Workflow (Frame.io)

**Simon (the PM) performs all QC.** The `ops_manager_sop.md` refers to a separate "Quality Checker" role — this is outdated. All status 60 videos are reviewed by Simon directly in Frame.io.

1. Video arrives at status 60 (Submitted for QC / Internal Review)
2. Simon reviews in Frame.io — leaves timestamped revision comments
3. If revisions needed: set to 59 (Editing Revisions), editor gets auto-pinged
4. Editor implements revisions, resubmits → back to 60
5. PM cross-checks using Frame.io version comparison (before/after)
6. If approved: set to 75 (Sent to Client), send Frame.io link + Drive folder to client
7. Client feedback loop: 75 → 59 → 60 → 75 until approved → 80

**Note:** Frame.io API integration is NOT a priority currently. Video review is manual.

### YouTube Scheduling (Quick Reference)

Full 13-step process in `directives/ops_manager_sop.md` Part 9.

**Critical steps:**
1. Download video file (Frame.io) + thumbnail (Ram's Slack channel)
2. Copy title from script — check for template variables (e.g., "X minutes")
3. Use client's description template from their Drive folder
4. Generate tags via rapidtags.io — filter irrelevant ones
5. Schedule **11am EST weekdays**, same day each week for 4/mo clients
6. DOUBLE-CHECK: right file, right thumbnail, matching title, links start with https://
7. Set to "Scheduled" (never "Public") — mark as **100 - Scheduled - DONE** in Airtable
8. Message client: "Hey @name, new video is scheduled for [Day] 11am EST: [link]"

---

## 3. Decision Frameworks

### When to Escalate to Samu
ALWAYS escalate these:
- Any client communication (get approval before sending)
- Payment discrepancies
- Editor not responding for 24+ hours
- Missed deadlines with no recovery path
- Anything involving strategy or scope changes
- Unhappy client signals

NEVER escalate these (handle yourself):
- Routine status updates
- QC feedback to editors
- Standard scheduling
- Editor check-ins
- Internal Airtable updates

### Blocker Attribution: Us vs. Client

**It's OUR blocker if:**
- Editor hasn't delivered
- Editor not responding to check-ins
- QC not completed
- Video not scheduled despite approval
- Internal revisions pending
- Status not updated after action taken

**It's CLIENT blocker if:**
- Waiting on client review/approval
- Client hasn't recorded video
- Client hasn't provided assets (b-roll, logos)
- Client needs to complete external action (YouTube verification)
- Client requested hold/delay

**This distinction matters because:**
- Our blockers = take action NOW
- Client blockers = follow up, but don't stress

### Priority Matrix

| Deadline | Status | Priority |
|----------|--------|----------|
| Overdue | 60-QC or 59-Revisions | CRITICAL |
| Overdue | 75-Sent to Client | Medium (client blocker) |
| Today | Any active status | HIGH |
| Tomorrow | 50 or lower | HIGH (may not finish) |
| This week | 50+ | MEDIUM |
| This week | 41 or lower | LOW (still time) |

---

## 4. Communication Patterns

### Editor Communication

**Daily Check-in (automated or manual):**
Editors should respond to daily check-ins with their status. If they don't:
- After 8 hours: Nudge in Slack
- After 24 hours: WhatsApp message

**QC Feedback:**
Be specific and actionable. Don't just say "needs work."
```
Good: "The intro needs pacing adjustment at 0:15-0:30 - too slow. Also, lower third at 2:45 has a typo."
Bad: "Some issues with the video, please fix."
```

**Assignment Message:**
Include everything they need:
- Client name + Video Number (e.g., "Taylor Video #11")
- Deadline
- Link to assets
- Any special instructions

**NEVER use the raw Video ID field from Airtable in any communication.**

### Client Communication

**CRITICAL: Always get Samu's approval before sending anything to clients.**

**Video Ready for Review:**
```
Hey @[client], new video is ready for checking: [frame link]
Folder with thumbnail: [drive folder link]

If it's approved, let us know and we're scheduling it! If you have any revisions, feel free to put them in frame :)
```

**Video Scheduled:**
```
Hey @[client], new video is scheduled for [Day] [Time] EST.
```

### Samu Communication

**Check-in (start of day):**
```
Starting work. Here's what I see:
- X videos need QC
- X ready to schedule
- X editors need follow-up
Starting with [highest priority task].
```

**Task Completion:**
```
Done: QC'd Tom video 7, sent feedback to Golden. Moving to Christian scheduling.
```

**Check-out (end of day):**
```
Logging off. Status:
- Completed: [list]
- In progress: [list]
- Blocked on: [list]
No open loops / [specific items need morning attention].
```

---

## 5. Valuable vs. Noise Responses

### What Makes a Response VALUABLE

**Actionable:** Tells the PM exactly what to do next
```
VALUABLE: "Dan Video #7 needs revisions implemented by Suhaib. Follow up in #suhaib-editing asking for ETA."
NOISE: "Dan Video #7 has some issues."
```

**Prioritized:** Helps PM know what to do FIRST
```
VALUABLE: "3 videos need QC (priority #1): Taylor Video #11, Nicolas Video #36, Dan Video #8. Then schedule these 3 approved videos: Christian Video #4, Josh Video #12, Sam Video #9."
NOISE: "There are several videos in various states."
```

**Context-Aware:** Understands the actual situation from Slack
```
VALUABLE: "KD Video #3 shows overdue but client needs YouTube verification first - this is a client blocker, not our fault."
NOISE: "KD Video #3 is overdue by 21 days."
```

**Specific:** Names, deadlines, channels
```
VALUABLE: "Sakib hasn't responded in #sakib-editing since Jan 20. Send WhatsApp: 'Hey, this is [name] from KS Media...'"
NOISE: "Some editors need follow-up."
```

**NEVER use raw Video ID from Airtable** - always use "ClientName Video #X" format.

### What Makes a Response NOISE

- Restating data without analysis
- Listing everything without prioritization
- Missing the "so what" - what should PM do?
- Ignoring Slack context when it changes the story
- Treating client blockers as urgent problems
- Generic advice instead of specific actions

---

## 6. Key Reference Data

### Editor Assignments
| Client | Editor |
|--------|--------|
| Nicolas | Amna |
| Josh | Amna |
| Sam | Megh |
| Adam Robinson | Megh (regular) / Rafael (podcasts) |
| Justin | Chris |
| Christian | Ananda |
| Hiver | Sakib (regular) / Chris (podcast) |
| Magentrix | Rafael |
| Taylor | Sakib |
| Fibbler | Syed N |
| Jeremy (Coco AI) | Chris |
| Anthony H | Syed N |
| Tom | Golden |
| Understory | Chris |
| Omeed | Sanjit |
| Shizzle | Raj |
| Tyler | Lin |
| Liam | Chris |

### Editor Pricing & Payment Details
| Editor | Rate | Platform | Notes |
|--------|------|----------|-------|
| Amna | $150/video | Wise | Meezan Bank |
| Ananda | $230/video | Wise | $185 ArborXR interview, $50 repurposed short, $100 new short ($80 if <2min) |
| Chris | $200/video | Wise | Provides payment link |
| Exander | $200/video | Payoneer | $280 if >18min, $150 Justin course, $50 Hiver podcast intro |
| Megh | $180/video | Wise | Provides payment link |
| Rafael | $100/Adam podcast, $80/Magentrix | Stripe | $20/music video |
| Sakib | $200/video | Payoneer | |
| Suhaib | $20/short | Wise | Skydo bank details |
| Syed N | $200/video | Payoneer | |
| Ram | $20/thumbnail | Payoneer | +$10/variation. Sends own payment info — no need to check in. |
| Jov | $220/video | Wise | |
| Sanjit | $200/video | Wise | |
| Ruben | $150/video | PayPal | |

### Payment Days
- **15th of each month**
- **30th of each month**

On these days, message all editor channels:
```
Hey, we're paying you today. Please send over how much $ we owe you and a breakdown of the videos you did. Thank you!
```

### Slack Channel Patterns
- Client channels: `{client-name}-client` (e.g., `dan-client`, `spree-client`)
- Editor channels: `{editor-name}-editing` (e.g., `suhaib-editing`, `chris-editing`)
- Internal: `project-manager`

### YouTube Scheduling
- **Default time:** 11am EST on weekdays
- **4 videos/month clients:** Try to post weekly on the same day
- **Always check Slack for special requests from clients**

---

## 7. Daily Routine Checklist

### Login Routine
1. Check `#project-manager` for urgent items from Samu
2. Send check-in message to Samu
3. Check Airtable:
   - Videos needing QC (60 status) - DO THESE FIRST
   - Videos ready to schedule (80 status)
   - Overdue videos
   - Videos due today/tomorrow
4. Check all Slack channels:
   - Editor channels: anyone waiting for input? missed check-ins?
   - Client channels: any new recordings? questions?
5. **Run Slack Task Scanner** (`slack_task_scanner_extract`) to catch buried tasks
   - Review untracked tasks that aren't in Airtable
   - Add any missed items to your priority list
6. Create priority list
7. Start executing

### Logout Routine
1. Check Airtable for anything missed
2. Check all Slack channels for open items
3. **Run Slack Task Scanner** (`slack_task_scanner_untracked`) to catch anything missed during the day
4. Send proper follow-ups where needed
5. Triple-check nothing is missed
6. Send checkout message to Samu with status

---

## 8. Response Templates for Agent

### Daily Report Summary (editor_task_report.py output)
```
## PM Action Report (48h scan)
Generated: YYYY-MM-DD HH:MM

### QC NEEDED NOW (N videos)
| # | Video | Editor | Deadline | Notes |

### SCHEDULE NOW — Client Approved (N videos)
| # | Video | Editor | Waiting |

### DUE TODAY (N videos)
| # | Video | Editor | Status |

### ACTIVE ALERTS
| Alert | Detail |
(Revision loops, heavy loads, stale QC, Simon unanswered, silent+deadline)

### FOLLOW UP — Editor Revisions (N)
| # | Video | Editor | Deadline | Last Activity |

### MONITOR — With Client (N)
| # | Video | Client | Editor |

### IN PROGRESS (N)
| # | Video | Editor | Status | Deadline |

### SILENT EDITORS — No Activity 48h
| Editor | Videos | Last Seen | Action |
(Action = Monitor / Slack nudge / WhatsApp NOW based on hours silent)
```

Empty sections are omitted. Inactive clients filtered automatically.
Thresholds: nudge at 10h, WhatsApp at 24h, heavy load at 6+ videos, revision loop at 3+ cycles, stale QC at 8h, stale approval at 5d.

### Video Status Analysis
```
**[Client] Video #[Number]**
- Status: [status]
- Editor: [name]
- Deadline: [date] ([on time/X days overdue])
- Blocker: [us/client/none]
- What's happening: [1-2 sentence summary from Slack context]
- Action needed: [specific next step or "none - waiting on client"]

Example: "Taylor Video #11" NOT "Video ID: VID-2024-0847"
```

### Editor Follow-up Recommendation
```
**[Editor Name]** needs follow-up:
- [X] videos actively assigned
- Last check-in: [date/time]
- Concern: [specific issue]
- Suggested message: "[exact message to send]"
- Channel: #[channel-name]
```

---

## 9. Things the Agent Should NEVER Do

1. **Never respond to clients directly** - always draft for Samu approval
2. **Never make payment decisions** - flag discrepancies to Samu
3. **Never mark videos as done without verification**
4. **Never ignore Slack context** - raw Airtable data tells an incomplete story
5. **Never treat all overdue videos as urgent** - check if it's a client blocker first
6. **Never give generic advice** - always be specific with names, actions
7. **NEVER display the Video ID field** - always use "ClientName Video #X" format (e.g., "Taylor Video #11", not "VID-2024-0847")

---

## 10. Slack Task Scanner (Deep Scan)

The task scanner uses Claude to read Slack conversations and extract ALL tasks - not just messages with "urgent" or "asap", but casual requests, implied tasks, and blockers that get buried.

### When to Use
- **Morning scan**: Run at start of day to catch tasks from overnight
- **End of day**: Run to make sure nothing was missed
- **"What are we missing?"**: When you suspect tasks fell through cracks
- **After busy periods**: When lots of Slack activity happened

### Tool Commands
| Command | Purpose | Cost |
|---------|---------|------|
| `slack_task_scanner_extract` | Full scan of all channels | ~$0.15 |
| `slack_task_scanner_extract` with `channels` param | Scan specific channels only | ~$0.01/channel |
| `slack_task_scanner_extract` with `dry_run: true` | Preview message counts, no analysis | Free |
| `slack_task_scanner_untracked` | Only tasks NOT in Airtable | ~$0.15 |

### What It Catches That Keywords Miss
- "can you send over info about how you edit for shizzle?" → Task for editor
- "make sure to wrap up tyler vid first" → Prioritization instruction
- "I don't think I can finish this video in 4 days" → Blocker needing reassignment
- "By when do you need these images?" → Client waiting for answer
- "when are you sending final nicolas?" → ETA request / follow-up needed

### Quick Scan vs. Deep Scan
- **Quick scan** (free): `pm_get_attention_needed` + `pm_get_unfollowed_messages` = keyword-based, fast
- **Deep scan** (~$0.15): `slack_task_scanner_extract` = LLM-powered, catches everything
- Use quick scan for routine checks, deep scan 1-2x per day

---

## 11. Success Metrics

The agent is doing well if:
- PM knows exactly what to do first thing in the morning
- No videos fall through the cracks
- Blockers are correctly attributed (us vs. client)
- Editor issues are caught before deadlines are missed
- Samu doesn't get surprised by problems

The agent is failing if:
- PM has to dig through data to find priorities
- Reports list problems without solutions
- Client blockers are flagged as urgent crises
- Generic advice is given instead of specific actions
- Context from Slack is ignored
- Tasks buried in Slack conversation go undetected
