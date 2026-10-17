"""Text normalisation and simple language detection, shared by training AND serving.

Why mask codes, phones and amounts but NOT links?
- The exact digits never matter, only that a code/phone/amount is present. Masking stops the model
  memorising specific numbers and lets it learn "a code + a request to share it" instead.
- Links are kept (with a zzurl marker added) because the domain itself is evidence: look-alike
  links such as "-verify" or "secure-login" are a classic scam tell, while the bank's official
  site is not. Masking links to one token cost ~10 points of test accuracy in our experiments.
- Mask tokens are plain words (zzcode, zzurl ...) so the TF-IDF tokenizer keeps them and they
  cannot be confused with the real word "code".
"""
import re
import unicodedata

URL_RE = re.compile(r"(https?://\S+|www\.\S+|\b\S+\.(?:example|com|lk|net|org)\S*)", re.I)
PHONE_RE = re.compile(r"\b0\d{1,2}[x\d]?[-\s]?[x\d]{3}[-\s]?[x\d]{4}\b", re.I)
AMOUNT_RE = re.compile(r"\b(?:lkr|rs\.?|ரூ\.?|රු\.?)\s*\d[\d,]*(?:\.\d+)?", re.I)
CODE_RE = re.compile(r"\b\d{4,8}\b")
NUM_RE = re.compile(r"\d[\d,]*")

SINHALA = re.compile(r"[඀-෿]")
TAMIL = re.compile(r"[஀-௿]")
SINGLISH_WORDS = {"eka", "oyage", "karanna", "kiyanna", "epa", "ewanna", "thiyenawa", "una", "nathi", "mama", "oya",
                  "machan", "malli", "akke", "ahanne", "puluwanda", "wenawa", "gedara", "karala", "ekak", "athulatha"}
TANGLISH_WORDS = {"unga", "pannunga", "sollunga", "illa", "aagiduchu", "irukku", "vaanga", "anupunga", "naan",
                  "machan", "kitta", "podunga", "pannadheenga", "sollaadheenga", "varen", "seri", "konjam"}


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFC", str(text))
    # masked text from the monitoring log (used when retraining on reviewed messages)
    t = t.replace("<CODE>", " zzcode ").replace("<PHONE>", " zzphone ").replace("<NUM>", " zznum ")
    t = URL_RE.sub(lambda m: " zzurl " + re.sub(r"[^a-z]+", " ", m.group(0).lower()) + " ", t)
    t = PHONE_RE.sub(" zzphone ", t)
    t = AMOUNT_RE.sub(" zzamt ", t)
    t = CODE_RE.sub(" zzcode ", t)
    t = NUM_RE.sub(" zznum ", t)
    t = t.lower()
    return re.sub(r"\s+", " ", t).strip()


def detect_lang(text: str) -> str:
    """Cheap script + keyword detector. Good enough for monitoring the language mix."""
    if SINHALA.search(text):
        return "si"
    if TAMIL.search(text):
        return "ta"
    words = set(re.findall(r"[a-z]+", text.lower()))
    s, t = len(words & SINGLISH_WORDS), len(words & TANGLISH_WORDS)
    if s == 0 and t == 0:
        return "en"
    return "singlish" if s >= t else "tanglish"


def tokens(text: str) -> list:
    """Word tokens of the normalised text, used for the unseen-word (OOV) share."""
    return re.findall(r"\w\w+", normalise(text))


# Rule-based red flags. They EXPLAIN a verdict to the user; the model makes the decision.
RED_FLAGS = [
    ("Asks you to share, send or read out a code, OTP or PIN",
     re.compile(r"(reply|send|share|forward|tell|read|type|enter|kiyanna|ewanna|sollunga|anupunga|podunga|reply pannunga|"
                r"එවන්න|කියන්න|அனுப்புங்கள்|சொல்லுங்கள்|பகிருங்கள்).{0,40}(otp|code|pin|password|reference|කේත|குறியீ)|"
                r"(otp|code|pin|reference).{0,40}(reply|send|share|tell|kiyanna|ewanna|sollunga|anupunga|එවන්න|කියන්න|அனுப்ப|சொல்)", re.I)),
    ("Contains a link that is not the bank's official site", re.compile(r"https?://\S*(verify|secure-login|login|bit\.)", re.I)),
    ("Tells you not to call your branch", re.compile(r"(do not|don't) call the branch|branch ekata call karanna epa|branch ku call panna vendam|ශාඛාව අමතන්න එපා|கிளையை அழைக்க வேண்டாம்", re.I)),
    ("Says it is 'only a reference number', not an OTP", re.compile(r"not an otp|only a reference|otp ekak nemey|otp illa|OTP එකක් නොවේ|OTP அல்ல", re.I)),
    ("Threatens to block, suspend or freeze your account", re.compile(r"block|suspend|deactivat|freeze|nawathanawa|අවහිර|நிறுத்த|முடக்க", re.I)),
]
SAFE_SIGNS = [
    ("Says never to share the code (typical of genuine bank messages)",
     re.compile(r"never share|do not share it|share karanna epa|share pannadheenga|yaarukkum sollaadheenga|නොකියන්න|பகிர வேண்டாம்", re.I)),
]


def explain(text: str) -> list:
    return [msg for msg, rx in RED_FLAGS if rx.search(text)]


def safe_signs(text: str) -> list:
    return [msg for msg, rx in SAFE_SIGNS if rx.search(text)]
