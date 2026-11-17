"""Deterministic leading-phrase Coroner labeler (REQ-COR-PHRASE).

The label table (`data/labels/coroner_labels.csv`) is keyed by the whole masked closure text, so it covers the few thousand
most common templates and misses the long tail: boilerplate prefixes ("Case Closed. Case Resolved ...", "Case Noted ...",
"Duplicate of Existing Case ...") followed by free text that is different on every case. This module labels those by their
leading phrase. It runs only for a closure the table does not list (the table, and a new-system Transitioned code, win), and
a text it cannot place stays `other` and unlabeled. No model, no randomness: the same text always gives the same label.

Order of the rules (the first that matches wins):
1. Backlog wording anywhere in the text: `bulk_backlog`.
2. Made-safe wording: `made_safe_temporary`.
3. Scheduled or listed wording: `planned_followup`.
4. A hand-off to an agency, utility or owner: `referred`, unless the text also says the work was completed.
5. The leading disposition word after the "Case Closed" boilerplate: duplicate, invalid, referred, noted, resolved.
6. A bare completed-work or no-action sentence with no disposition word (the legacy closure reasons of city crews).
"""

from __future__ import annotations

import re

_BOILER = re.compile(r"^(?:case\s+closed\b[\s.:]*)+")
_LEAD = re.compile(
    r"^(?:case\s+)?(?P<word>resolved|noted|invalid|referred|duplicate|closed|expired|rejected|withdrawn|cancel(?:l)?ed)\b"
)

BACKLOG = re.compile(
    r"due to the age of|age of (?:the|this) request|we apologi[sz]e for the time it has taken|now consider this (?:service )?request closed"
    r"|old service request|\bexpired\b|\bbacklog\b|closing out|clean ?up of (?:old|open)|mass(?:ive)? clos"
)
MADE_SAFE = re.compile(
    r"made safe|make safe|made-safe|temporar(?:y|ily)|cold ?patch|temp(?:\.)? patch|safety improvements? were made|safety measures"
    r"|barricad|coned off|plated|steel plate|secured the (?:area|hole|hazard)"
)
PLANNED = re.compile(
    r"patch list|added to (?:the |our )?(?:list|schedule|queue|program|capital)|on (?:the|a|our) (?:list|schedule|queue)"
    r"|will be (?:scheduled|repaired|replaced|fixed|addressed|completed|done|installed|resurfaced|paved|included)"
    r"|has been (?:scheduled|queued|forwarded to the (?:crew|contractor))|is scheduled|are scheduled|scheduled for|work order"
    r"|(?:program|project) (?:runs|will|is)|permanent (?:repair|restoration|fix) (?:will|is|has)|(?:in|for) (?:the )?(?:next|upcoming|spring|summer)"
    r"|capital (?:plan|program|project)|repaving|resurfacing (?:program|project|schedule)|will take care|put on|placed on"
    r"|engineer (?:has been|will)|evaluat(?:e|ed|ion) (?:by|from)"
)
REFERRED = re.compile(
    r"referred to|has been referred|forwarded to|reallocated|sent to (?:the )?(?:\w+ ){0,3}(?:department|agency|utility|company|owner|contractor)"
    r"|jurisdiction of|external agency|(?:is|are) (?:the )?responsib(?:le|ility) (?:of|for)|responsibility of|notified (?:the )?(?:\w+ ){0,3}"
    r"(?:bwsc|national grid|eversource|verizon|comcast|utility|mbta|massdot|mass dot|dcr|massport|msba|owner|abutter|contractor|"
    r"water and sewer|dpw|state|property)|per public (?:works|works dept)|private (?:property|way|owner)|not (?:a )?city (?:of boston )?"
    r"(?:property|street|road|responsib)|state (?:road|highway|owned)|(?:bwsc|national grid|eversource|mbta|massdot|dcr|massport)"
)
DONE = re.compile(
    r"\b(?:repaired|replaced|replace|filled|fixed|installed|removed|cleaned|cleared|restored|resurfaced|patched|completed|"
    r"respliced|repair(?:ed)? made|re-?set|swept|picked up|cut|trimmed|painted|reinstalled|straightened|tightened|swapped|"
    r"changed|rewired|lamped|re-?lamped|bulb|photo ?cell|ran new|new (?:wire|cable|fixture|pole|sign|post))\b"
)
NO_ACTION = re.compile(
    r"no (?:problem|issue|violation|work|action|defect|hazard|trouble|damage|repair)|nothing (?:found|to|wrong)|not (?:found|needed|necessary|"
    r"applicable|an issue|a problem)|unable to (?:locate|find|verify|determine|identify|contact|access|complete)|could not (?:locate|find|"
    r"verify|identify|determine|contact)|cannot (?:locate|find|verify|identify|determine|reproduce)|couldn'?t (?:locate|find)|"
    r"insufficient|not enough information|incomplete|too little|no longer (?:an issue|needed|exists|there)|already (?:repaired|fixed|done|"
    r"resolved|completed)|light is (?:on|working)|lights? (?:is|are) (?:on|working)|all clear|checked and (?:working|ok|okay)|working (?:properly|"
    r"fine|ok)|no trouble found|is working"
)
INVALID_TEXT = re.compile(
    r"test (?:case|request|call)|not a valid|invalid|not enough information|insufficient information|too little information|"
    r"does not exist|no such|wrong (?:address|number|department)|not a (?:311|city)|prank|spam|sorry,? we (?:are )?(?:unable|could not|cannot)"
    r"|unable to (?:locate|identify|determine)|could not (?:locate|identify)|cannot (?:locate|identify)|please (?:re-?submit|resubmit|submit)"
    r"|need(?:s|ed)? (?:a |an )?(?:better|more|picture|photo|location|address|information|specific)|more information|(?:do|does) not (?:coordinate|match)"
    r"|no record|^test\b|\btest\b$|no (?:problem|issue|violation|defect|hazard|trouble|loose|open)\b.*\bfound|nothing (?:found|wrong)"
)
DUP_TEXT = re.compile(r"duplicate|already (?:reported|open|have a case|submitted)|same (?:issue|request|location) (?:as|was)|existing case")
TRANSFER_TEXT = re.compile(r"resubmitted as|see new case|new case (?:has been created|number|entered|ref|#)|transferr?ed|migrat|transition(?:ed)? to")


def strip_boilerplate(template: str) -> str:
    """The masked template without its "case closed" boilerplate prefix."""
    return _BOILER.sub("", template.strip()).strip(" .:-")


def phrase_label(template: str) -> str | None:
    """The leading-phrase label of a masked closure template, or None when no rule places it (REQ-COR-PHRASE.1)."""
    body = strip_boilerplate(template)
    if not body:
        return None
    if TRANSFER_TEXT.search(body):
        return "referred"  # a transfer or hand-off to the new system (the table labels these `referred` as well)
    if BACKLOG.search(body):
        return "bulk_backlog"
    lead = _LEAD.match(body)
    word = lead.group("word") if lead else None
    rest = body[lead.end():].strip(" .:-") if lead else body
    if word in {"duplicate"} or re.match(r"^(?:case\s+)?(?:noted|resolved|closed)?\W*duplicate", body):
        return "duplicate"
    if word in {"invalid", "rejected", "withdrawn", "cancelled", "canceled"}:
        return "invalid"
    if MADE_SAFE.search(rest):
        return "made_safe_temporary"
    if PLANNED.search(rest):
        return "planned_followup"
    if word == "referred":
        return "referred"
    if REFERRED.search(rest) and not (word == "resolved" and DONE.search(rest) and not re.search(r"notified|referred|forwarded|jurisdiction", rest)):
        return "referred"
    if word == "noted":
        if DUP_TEXT.search(rest):
            return "duplicate"
        if INVALID_TEXT.search(rest) and not DONE.search(rest):
            return "invalid"
        return "resolved" if DONE.search(rest) else "noted"  # "noted" with completed work described is resolved (table rationale)
    if word == "resolved":
        if INVALID_TEXT.search(rest) and not DONE.search(rest):
            return "invalid"  # no problem found, too little information (table: `invalid`)
        return "resolved"
    if word in {"closed", "expired"}:
        return "bulk_backlog" if word == "expired" else None
    if DUP_TEXT.search(body):
        return "duplicate"
    if INVALID_TEXT.search(body):
        return "invalid"
    if DONE.search(body):
        return "resolved"
    if NO_ACTION.search(body):
        return "noted"
    return None
