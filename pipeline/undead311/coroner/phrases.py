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

"Case Noted" closures (REQ-COR-NOTED) follow rule 5 differently: they stay `noted` unless the text affirms completed work
with no negation, hand-off or temporary cue. Signatures and sign-off text are cut off before any cue is matched, so a name
or a closing line ("Regards, ... Eversource ...") cannot trigger one. Order for a "Case Noted" text: temporary cue
(`made_safe_temporary`), scheduled wording (`planned_followup`), hand-off cue (`referred`), duplicate wording, the location
could not be found (`invalid`), no-problem or too-little-information wording (`invalid`), a negation (`noted`), completed
work (`resolved`), and otherwise `noted`.
"""

from __future__ import annotations

import re

from undead311.ingest.pii import strip_signoff

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
# REQ-COR-NOTED: the cues for a "Case Noted" text. Each extends the general rule above with the wording found in the data.
NOTED_TEMPORARY = re.compile(
    MADE_SAFE.pattern + r"|\btemp\b|for the time being|\bbarrels?\b|\bcones?\b|(?<!root )(?<!license )(?<!vehicle )\bplates?\b(?! number)"
    r"|picked up (?:the |a |an )?(?:(?:down(?:ed)?|knocked(?:[- ]down)?|damaged|fallen|bent) )?(?:sign|pole|post)s?\b"
)
_CUE_NEGATED = re.compile(r"\b(?:no|not|neither|nor|without|any)\W+(?:\w+\W+){0,2}$")  # "no cone found", "neither banging nor loose plate"
_CUE_NEGATED_AFTER = re.compile(r"\W*(?:(?:is|are|was|were)\W+)?(?:neither|not|never)\b")  # "the plate is neither banging nor loose"
NOTED_HANDOFF = re.compile(
    REFERRED.pattern + r"|\breferred\b|contractor (?:has been |was |is |will be |have been )?(?:notified|contacted|informed|called)"
    r"|privately[ -]owned|private (?:alley|land|lot|driveway)|owners?(?:'s|s')? (?:must|needs? to|will need to|has to|have to|should)"
    r"|(?:property )?owners? (?:is|are) responsib|new (?:service )?(?:request|case) (?:has been |was |is )?(?:created|opened|entered|submitted|generated)"
    r"|national grid|ngrid|ngrdi|eversource|nstar|bwsc|verizon|comcast|boston gas|keyspan|\brcn\b"
    r"|(?:sent|forwarded|issued|passed) (?:this |the |it )?(?:\w+ ){0,2}(?:over )?to (?:the )?(?:utility|contractor|owner)"
)
# Wording that says the work is not (yet) done, was not needed, or found nothing: a negation cue.
NOTED_NEGATION = re.compile(
    r"\bno\b(?! (?:stopping|parking|standing|turn|u-turn|trucks?|entry|outlet|through|left|right|trespassing|dumping|littering"
    r"|smoking|loading|enter|exit|passing|thru|outlet)\b)|\bnot\b|\b(?:isn|wasn|aren|doesn|didn|don|won|hasn|haven|couldn|wouldn|shouldn|can)['\u2019]?t\b|nothing\b|\bnone\b|\bnor\b|\bever\b|unable to|could not|cannot|insufficient"
    r"|not enough information|incomplete|no longer|light is (?:on|working)|lights? (?:is|are) (?:on|working)|all clear"
    r"|working (?:properly|fine|ok)|no trouble found|is working|\bno [a-z' -]{1,30}\bfound\b|\bneither\b|\bnever\b"
    r"|not (?:yet )?(?:been )?(?:completed|repaired|fixed|done|replaced|installed)|(?:has|have) not been"
    r"|\bwill\b|going to|\bto be\b|\bbeing\b|\bwaiting\b|under construction|discontinued|has been issued to|issued to"
    r"|when [^.]{0,60}completed|after (?:the )?winter"
)
LOCATION_NOT_FOUND = re.compile(
    r"(?:location|address|site|intersection|street|spot)\b[^.]{0,40}\b(?:could not|cannot|can'?t|couldn'?t|unable to|not)\b[^.]{0,15}"
    r"\b(?:locat(?:e|ed)|found|find)\b"
    r"|\b(?:could not|cannot|can'?t|couldn'?t|unable to)\b (?:be )?(?:locate|find|found)\b[^.]{0,40}\b(?:location|address|site|intersection|street)\b"
    r"|no such (?:address|location|street)|(?:location|address) (?:not found|does not exist)"
    r"|(?:provide|need|send)\b[^.]{0,30}\b(?:correct|better|exact|accurate|specific) (?:location|address)"
    r"|(?:better|more accurate|more specific|exact) location"
)
INSPECTION_ONLY = re.compile(r"(?:visual )?inspection (?:was )?completed|inspected")  # an inspection is not completed work
DUP_TEXT = re.compile(r"duplicate|already (?:reported|open|have a case|submitted)|same (?:issue|request|location) (?:as|was)|existing case")
TRANSFER_TEXT = re.compile(r"resubmitted as|see new case|new case (?:has been created|number|entered|ref|#)|transferr?ed|migrat|transition(?:ed)? to")


def strip_boilerplate(template: str) -> str:
    """The masked template without its "case closed" boilerplate prefix."""
    return _BOILER.sub("", template.strip()).strip(" .:-")


def is_noted_lead(template: str) -> bool:
    """True when a masked closure template starts with "Case Noted" after the "case closed" boilerplate (REQ-COR-NOTED.1)."""
    lead = _LEAD.match(strip_boilerplate(template))
    return bool(lead and lead.group("word") == "noted")


def noted_cue(rest: str) -> str | None:
    """The label a cue in the text after "Case Noted" gives, or None when the text has no cue (REQ-COR-NOTED.2-5). The sign-off
    is cut first, so a signature or a closing line cannot supply a cue. A negation gives `noted`."""
    rest = strip_signoff(rest)
    if any(
        not _CUE_NEGATED.search(rest[: m.start()]) and not _CUE_NEGATED_AFTER.match(rest[m.end():])
        for m in NOTED_TEMPORARY.finditer(rest)
    ):
        return "made_safe_temporary"
    if PLANNED.search(rest):
        return "planned_followup"
    if NOTED_HANDOFF.search(rest):
        return "referred"
    if DUP_TEXT.search(rest):
        return "duplicate"
    if LOCATION_NOT_FOUND.search(rest):
        return "invalid"
    if INVALID_TEXT.search(rest) and not DONE.search(rest):
        return "invalid"
    if NOTED_NEGATION.search(rest):
        return "noted"
    return None


def noted_label(rest: str, fallback: str = "noted") -> str:
    """The label of the text after "Case Noted": `noted` unless the text affirms completed work with no negation, hand-off or
    temporary cue (REQ-COR-NOTED.2-4). `fallback` is the label of a text with no cue and no completed-work word."""
    cue = noted_cue(rest)
    if cue:
        return cue
    return "resolved" if DONE.search(INSPECTION_ONLY.sub("", strip_signoff(rest))) else fallback


def _noted_rest(template: str) -> str | None:
    """The text after the "Case Noted" lead of a masked template, or None when the template does not start that way."""
    body = strip_boilerplate(template.replace("[removed]", " "))
    lead = _LEAD.match(body)
    if lead is None or lead.group("word") != "noted":
        return None
    return body[lead.end():].strip(" .:-")


def recheck_table_label(template: str, table_label: str) -> str:
    """The label of a "Case Noted" template that the label table calls `resolved` or `noted` (REQ-COR-NOTED.6). Only a cue
    changes the table's label: a hand-off, temporary, scheduled, duplicate or invalid wording moves either label; a negation
    moves `resolved` to `noted`. A text with no cue keeps the table's label, so the table is never made to say `resolved`."""
    label = phrase_label(template)
    if label not in (None, "resolved", "noted"):
        return label  # type: ignore[return-value]
    rest = _noted_rest(template)
    if label == "noted" and table_label == "resolved" and rest is not None and noted_cue(rest) == "noted":
        return "noted"
    return table_label


def phrase_label(template: str) -> str | None:
    """The leading-phrase label of a masked closure template, or None when no rule places it (REQ-COR-PHRASE.1)."""
    body = strip_boilerplate(template.replace("[removed]", " "))  # a scrubbed marker is not wording ("removed" is a work word)
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
    if word == "noted":
        return noted_label(rest)  # REQ-COR-NOTED
    if MADE_SAFE.search(rest):
        return "made_safe_temporary"
    if PLANNED.search(rest):
        return "planned_followup"
    if word == "referred":
        return "referred"
    if REFERRED.search(rest) and not (word == "resolved" and DONE.search(rest) and not re.search(r"notified|referred|forwarded|jurisdiction", rest)):
        return "referred"
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
