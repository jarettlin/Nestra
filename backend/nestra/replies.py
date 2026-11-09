"""Makes Nestra's spoken replies sound less robotic.

The command processor writes plain, predictable replies ("Fan turned on.").
For voice, this rephrases them a little each time and adds a short
acknowledgement, and handles the small talk around a conversation
("thank you", "that's all").
"""

from __future__ import annotations

import random
import re

_rng = random.Random()

ACKS = ["", "", "Sure. ", "Done. ", "Okay, ", "You got it. ", "All set. ", "Alright, ", "No problem. "]

# "{name} turned on" said a few different ways.
SWITCHED = {
    "on": ["{name} turned on", "{name} is on now", "I've switched on the {name}", "The {name} is on", "Switched on the {name}"],
    "off": ["{name} turned off", "{name} is off now", "I've switched off the {name}", "The {name} is off", "Switched off the {name}"],
}
MANY = {
    "on": ["Turned on {n} devices {where}", "{n} devices are on {where}", "I've switched on {n} devices {where}"],
    "off": ["Turned off {n} devices {where}", "{n} devices are off {where}", "I've switched off {n} devices {where}",
            "Everything's off {where}: {n} devices"],
}
# Words that lose their capital after "Okay, " (names like "Main Light" keep theirs).
_LOWER_AFTER_COMMA = {"The", "Turned", "Switched", "Everything", "Everything's"}
WAKE_REPLIES = ["Yes?", "I'm listening.", "How can I help?", "Hi! What can I do?", "Yes, what do you need?"]
FOLLOW_UPS = ["Anything else?", "What else can I do?", "Need anything else?", "Anything else I can help with?"]
UNCLEAR = [
    "Sorry, I didn't get that. Could you say it again?",
    "Hmm, I'm not sure what to control. Try something like \"turn on the bedroom light\".",
    "I didn't catch which device you meant. Could you rephrase?",
]
GOODBYES = [
    "You're welcome!", "Anytime.", "Happy to help.", "No problem, I'll be here.",
    "Sure thing. Just say Hi Nestra if you need me.", "Okay. Call me if you need anything.",
]

_SWITCHED = re.compile(r"^(?P<name>.+?) turned (?P<state>on|off)$")
_MANY = re.compile(r"^Turned (?P<state>on|off) (?P<n>\d+) devices (?P<where>.+)$")
# Ways of ending the conversation: "thanks", "that's all", "no that's it", "goodbye", "nothing".
_DONE = re.compile(
    r"^\W*(?:(?:no|nope|nah|okay|ok|alright|great|cool|perfect|good)\W+)*"
    r"(?:thanks?(?: you)?(?: so much| very much)?|thank you(?: nestra)?|cheers|that(?:'?s| is) (?:all|it|everything|good|fine|enough)"
    r"|that will be all|nothing(?: else)?(?: thanks?)?|no(?:thing)? more|i'?m (?:good|done|fine|okay|all set)"
    r"|all good|good ?bye|bye|see you|never ?mind|stop|cancel|that'?s all for now|no thanks?)"
    r"(?:\W+(?:nestra|thanks?|thank you|bye|for now|that'?s all|that'?s it))*\W*$",
    re.IGNORECASE,
)

_YES = re.compile(r"^\W*(?:yes|yeah|yep|yup|sure|ok(?:ay)?|go ahead|do it|please do|confirm(?:ed)?|correct|right)(?:\W+(?:please|go ahead|do it|nestra|thanks?))*\W*$", re.I)
_NO = re.compile(r"^\W*(?:no|nope|nah|don'?t|do not|cancel|stop|never ?mind|leave it)(?:\W+(?:thanks?|don'?t|do not|leave it|never ?mind|nestra))*\W*$", re.I)
DECLINED = ["Okay, I won't.", "Alright, leaving it as it is.", "No problem, cancelled."]


def is_yes(text: str) -> bool:
    return bool(_YES.match(text.strip()))


def is_no(text: str) -> bool:
    return bool(_NO.match(text.strip()))


def declined() -> str:
    return _rng.choice(DECLINED)


def is_goodbye(text: str) -> bool:
    """Does this end the conversation? ('thank you', "that's all", 'no thanks'...)"""
    return bool(_DONE.match(text.strip()))


def goodbye() -> str:
    return _rng.choice(GOODBYES)


def _rephrase_sentence(sentence: str) -> str:
    body = sentence.rstrip(".")
    if m := _SWITCHED.match(body):
        return _rng.choice(SWITCHED[m["state"]]).format(name=m["name"]) + "."
    if m := _MANY.match(body):
        return _rng.choice(MANY[m["state"]]).format(n=m["n"], where=m["where"]) + "."
    return sentence


def friendly(result: dict, *, follow_up: bool = False) -> dict:
    """Rephrase a command result's reply for speaking. Returns a new dict."""
    reply = result.get("reply", "")
    if result.get("ok"):
        sentences = re.split(r"(?<=[.!?])\s+", reply.strip())
        reply = " ".join(_rephrase_sentence(s) for s in sentences if s)
        ack = _rng.choice(ACKS)
        if ack:
            first = reply.split(" ", 1)[0]
            lower = ack.endswith(", ") and first in _LOWER_AFTER_COMMA
            reply = ack + (reply[0].lower() + reply[1:] if lower else reply)
        if follow_up and _rng.random() < 0.6:
            reply += " " + _rng.choice(FOLLOW_UPS)
    elif reply.startswith("Sorry, I couldn't tell what to control"):
        reply = _rng.choice(UNCLEAR)
    return {**result, "reply": reply}


def wake_reply() -> str:
    return _rng.choice(WAKE_REPLIES)
