"""
Centralized Airtable status constants for all PM scripts.
Single source of truth — prevents status name drift across scripts.
"""

# ---------------------------------------------------------------------------
# Canonical Airtable Editing Status values
# ---------------------------------------------------------------------------

# All active (non-completed) editing statuses
ALL_ACTIVE_STATUSES = [
    "40 - Client Sent Raw Footage",
    "41 - Sent to Editor",
    "50 - Editor Confirmed",
    "59 - Editing Revisions",
    "60 - Submitted for QC",
    "60 - Internal Review",             # dual variant — same meaning
    "70 - Approved By Agency",
    "75 - Sent to Client For Review",
    "80 - Approved By Client",
    "90 - Approved But On Hold",
]

# Status 60 has two Airtable variants; both mean "PM needs to review"
QC_STATUSES = ["60 - Submitted for QC", "60 - Internal Review"]

# Statuses where the video is actively with the editor
EDITOR_ACTIVE_STATUSES = [
    "41 - Sent to Editor",
    "50 - Editor Confirmed",
    "59 - Editing Revisions",
]

# Status progression order (numeric)
STATUS_ORDER = {
    "Waiting For Input From Client": 35,
    "40 - Client Sent Raw Footage": 40,
    "41 - Sent to Editor": 41,
    "50 - Editor Confirmed": 50,
    "59 - Editing Revisions": 59,
    "60 - Submitted for QC": 60,
    "60 - Internal Review": 60,
    "70 - Approved By Agency": 70,
    "75 - Sent to Client For Review": 75,
    "80 - Approved By Client": 80,
    "90 - Approved But On Hold": 90,
    "100 - Scheduled - DONE": 100,
}

# Short labels for compact display
STATUS_SHORT = {
    "40": "raw",
    "41": "assigned",
    "50": "editing",
    "59": "revision",
    "60": "QC",
    "70": "agency ok",
    "75": "client rev",
    "80": "approved",
    "90": "on hold",
    "100": "done",
}

# ---------------------------------------------------------------------------
# Deadline semantics
# ---------------------------------------------------------------------------
# IMPORTANT: Deadline in Airtable = V1 delivery date (first draft).
# Set 3 days from "Sent to Editor". Does NOT mean final delivery.
# A video past deadline but in revision cycles (59/75) is normal.
DEADLINE_SEMANTICS = "V1 delivery (first draft), 3 days from editor assignment"

# ---------------------------------------------------------------------------
# Client status filtering
# ---------------------------------------------------------------------------
INACTIVE_CLIENT_STATUSES = ["Archive", "Inactive", "Paused", "Churned", "Lost"]

# ---------------------------------------------------------------------------
# Escalation timing (SOP Part 5)
# ---------------------------------------------------------------------------
EDITOR_NUDGE_HOURS = 10       # Slack nudge after no check-in response
EDITOR_WHATSAPP_HOURS = 24    # WhatsApp escalation after no response
CLIENT_RESPONSE_SLOW_HOURS = 4  # Flag as slow response (SOP says 20min; 4h for avg threshold)

# ---------------------------------------------------------------------------
# Alert thresholds
# ---------------------------------------------------------------------------
HEAVY_LOAD_THRESHOLD = 6       # Editor has this many+ active videos = alert
REVISION_LOOP_THRESHOLD = 3    # Video bounced 59→60 this many+ times = alert
STALE_QC_HOURS = 8             # QC submitted 8h+ ago and not reviewed = alert
STALE_APPROVAL_DAYS = 5        # Video at status 80 for 5+ days = alert

# ---------------------------------------------------------------------------
# PM / ops manager identities
# ---------------------------------------------------------------------------
SIMON_SLACK_USER_ID = "U09SVR0R2GH"  # Simon (PM/ops manager)
SAMU_SLACK_USER_ID = "U070CUSP75M"   # Samu (ops manager / task giver)
OPS_MANAGER_IDS = {
    "U09SVR0R2GH",  # Simon
}

# ---------------------------------------------------------------------------
# Deadline filtering
# ---------------------------------------------------------------------------
# Statuses where V1 delivery is already done (exclude from DUE TODAY).
# NOTE: 75 (Sent to Client) is NOT excluded — videos bounce back to revisions
# so deadline is still relevant until client approves.
POST_DEADLINE_STATUSES = [
    "80 - Approved By Client",
    "90 - Approved But On Hold",
    "100 - Scheduled - DONE",
]

# ---------------------------------------------------------------------------
# Thumbnail pipeline (SOP Part 7 — Ram manages these, PM only sets "New")
# ---------------------------------------------------------------------------
# Actual Airtable "Thumbnail Status" values (verified 2026-03-02):
#   "00 - New"                      → needs thumbnail
#   "In Progress"                   → Ram is working on it
#   "Thumbnail Sent For Revision"   → sent back to Ram for changes
#   "Thumbnail Approved"            → done
THUMBNAIL_NEEDS_WORK = "00 - New"
THUMBNAIL_IN_PROGRESS = "In Progress"
THUMBNAIL_IN_REVISION = "Thumbnail Sent For Revision"
THUMBNAIL_APPROVED = "Thumbnail Approved"
THUMBNAIL_ACTIVE_STATUSES = [THUMBNAIL_NEEDS_WORK, THUMBNAIL_IN_PROGRESS, THUMBNAIL_IN_REVISION]
RAM_CHANNEL_ID = "C070JMABW07"


# ---------------------------------------------------------------------------
# Stale status thresholds (crosscheck report)
# ---------------------------------------------------------------------------
# Maximum expected days at each status before flagging as stale.
# Based on SOP: deadline = V1 delivery 3 days from assignment.
STATUS_STALE_DAYS = {
    "60 - Submitted for QC": 2,        # Simon needs to review — he's the bottleneck
    "60 - Internal Review": 2,
    "80 - Approved By Client": 2,      # Needs scheduling — Simon's job
}

# ---------------------------------------------------------------------------
# Valid status transitions (reflects actual practice, not theoretical SOP)
# ---------------------------------------------------------------------------
VALID_TRANSITIONS = {
    "41 - Sent to Editor":            ["50 - Editor Confirmed"],
    "50 - Editor Confirmed":          ["59 - Editing Revisions", "60 - Submitted for QC"],
    "59 - Editing Revisions":         ["60 - Submitted for QC", "60 - Internal Review"],
    "60 - Submitted for QC":          ["59 - Editing Revisions", "75 - Sent to Client For Review"],
    "60 - Internal Review":           ["59 - Editing Revisions", "75 - Sent to Client For Review"],
    "75 - Sent to Client For Review": ["59 - Editing Revisions", "80 - Approved By Client"],
    "80 - Approved By Client":        ["100 - Scheduled - DONE", "90 - Approved But On Hold"],
}

# ---------------------------------------------------------------------------
# Frame.io integration
# ---------------------------------------------------------------------------
FRAMEIO_LINK_FIELDS = ["Frame.io Link", "Frame Link", "Review Link"]

# Crosscheck thresholds
STALE_INPUT_DAYS = 14             # Flag "Waiting For Input" after this many days
FRAMEIO_FOLLOWUP_DAYS = 5         # Flag status-75 videos with no Frame.io activity
APPROVAL_KEYWORDS = [
    "approved", "love it", "looks great", "good to go", "all good",
    "go ahead", "perfect", "approve", "happy with it", "good to post",
    "ready to post", "ready to go", "looks good", "looks amazing",
]
FOOTAGE_KEYWORDS = [
    "recorded", "footage", "uploaded", "new video", "raw", "just sent",
    "finished recording", "done recording", "sent the video",
    "sent the recording", "here's the video", "here is the video",
]
