import re

def stem_word(w: str) -> str:
    """
    Applies simple English suffix stemming rules to find the base form of a word.
    Handles common running biometrics terms (e.g. 'pulled' -> 'pull', 'soreness' -> 'sore').
    """
    w_lower = w.lower()
    
    # Noun suffixes
    if w_lower.endswith("ness") and len(w_lower) > 6:
        return w_lower[:-4]
        
    # Plural / singular
    if w_lower.endswith("ies") and len(w_lower) > 5:
        return w_lower[:-3] + "y"
    if w_lower.endswith("es") and len(w_lower) > 4:
        if w_lower.endswith("aches"):
            return "ache"
        return w_lower[:-2]
    if w_lower.endswith("s") and not w_lower.endswith("ss") and len(w_lower) > 2:
        return w_lower[:-1]
        
    # Past tense
    if w_lower.endswith("ed") and len(w_lower) > 4:
        if w_lower.endswith("ied"):
            return w_lower[:-3] + "y"
        stemmed = w_lower[:-2]
        if len(stemmed) > 3 and stemmed[-1] == stemmed[-2]:
            if stemmed[-1] in {"g", "n", "p", "t", "d", "b", "r"}:
                return stemmed[:-1]
        return stemmed
        
    # Gerund / continuous
    if w_lower.endswith("ing") and len(w_lower) > 5:
        stemmed = w_lower[:-3]
        if len(stemmed) > 3 and stemmed[-1] == stemmed[-2]:
            if stemmed[-1] in {"g", "n", "p", "t", "d", "b", "r"}:
                stemmed = stemmed[:-1]
        if stemmed in {"ach", "twing", "tir", "chaf", "inflam", "bruis", "energiz"}:
            return stemmed + "e"
        return stemmed
        
    return w_lower


def detect_sentiment(feedback: str) -> str:
    """
    Parses subjective athlete feedback, classifying it into pain, fatigue, 
    high-energy, or neutral sentiment. Uses stemming, negation-aware keyword context 
    matching, and a relative scoring algorithm to prevent false-positives 
    (e.g., 'not tired' or 'no pain' triggering fatigue/pain).
    """
    feedback_lower = feedback.lower()
    
    # 0. Pre-process common idioms and phrases to prevent negation false-positives
    idioms = {
        "never better": "great",
        "not bad": "good",
        "no problem": "fine",
        "can't wait": "excited",
        "cant wait": "excited",
        "nothing hurts": "healthy",
        "no pain": "healthy",
        "zero pain": "healthy",
        "pain free": "healthy",
        "pain-free": "healthy",
        "under the weather": "sick",
        "run down": "exhausted",
        "worn out": "exhausted",
        "feel like a million bucks": "great",
        "feeling like a million bucks": "great",
        "ready to roll": "ready",
        "good to go": "ready",
        "fit as a fiddle": "healthy",
        "on top of the world": "great",
        "raring to go": "ready",
        "hit the wall": "exhausted",
        "running on empty": "exhausted",
        "run on empty": "exhausted",
        "feeling blue": "bad",
        "feel blue": "bad",
        "stiff as a board": "stiff",
        "no soreness": "healthy",
        "not sore": "healthy",
        "not tired": "fresh"
    }
    for idiom, replacement in idioms.items():
        feedback_lower = feedback_lower.replace(idiom, replacement)
        
    # 1. Expanded Pain / injury indicators (base forms and common inflections)
    pain_keywords = {
        "sore", "pain", "hurt", "tight", "stiff", "cramp", "ach", "injury", "ache", "twinge", "pull",
        "sprain", "strain", "twist", "tear", "break", "fracture", "snap", "pop", "tweak", "bruise",
        "bruis", "swell", "swollen", "swelling", "inflame", "inflam", "inflammation", "torn", "broken",
        "blister", "chafe", "chaf", "splint", "tendonitis", "itbs", "fasciitis", "ankle", "knee", "calf",
        "quad", "hamstring", "foot", "shin", "heel", "sole", "plantar", "achilles", "groin", "back",
        "hip", "joint", "shoulder", "neck", "wrist", "elbow", "muscle", "tendon", "ligament", "bone",
        "patella", "meniscus", "spasming", "spasm", "restricted", "throbbing", "stabbing", "sharp",
        "dull", "tender", "aching", "painful", "tweaked", "pulled", "sprained", "strained", "torn",
        "ruptured", "rupture", "dislocate", "dislocated", "chafing"
    }
    
    # 2. Expanded Fatigue / exhaustion / severe under-recovery indicators (base forms and common inflections)
    fatigue_keywords = {
        "tired", "exhausted", "fatigue", "sleepy", "weak", "heavy", 
        "dead", "wrecked", "lazy", "beat", "flat", "stuck", "drained", 
        "sluggish", "bad", "terrible", "horrible", "awful", "poor", "exhaustion", "tire",
        "burnout", "overtrain", "winded", "gasping", "drowsy", "lethargic", "knackered",
        "shattered", "fried", "wasted", "spent", "pooped", "groggy", "restless", "fatigued",
        "sick", "ill", "flu", "cold", "fever", "cough", "nausea", "dizzy", "headache",
        "throat", "congested", "congestion", "runny", "sneeze", "unwell", "nauseous",
        "hangover", "hungover", "migraine", "exhaust", "worn"
    }
    
    # 3. Expanded High energy / readiness indicators (including positive exercise/movement verbs)
    high_energy_keywords = {
        "ready", "dominate", "go", "good", "great", "strong", "perfect", 
        "fresh", "fast", "pace", "hard", "more", "fit", "healthy", 
        "fine", "well", "yes", "excited", "fly", "destroy", "amazing", "awesome",
        "run", "walk", "move", "train", "workout", "exercise", "jog", "lift",
        "pump", "hype", "energize", "energiz", "unstoppable", "stronger", "better",
        "superb", "fantastic", "energized", "recovered", "rested", "peppy", "charged",
        "recharged", "vitality", "pumped", "crushing", "crush"
    }
    
    # 4. Negation tokens that invert positive/negative statements
    negations = {
        "not", "no", "never", "dont", "don't", "cant", "can't", "neither", 
        "nothing", "without", "won't", "wont", "cannot", "hardly", "scarcely", 
        "barely", "zero", "free"
    }

    # Extract words using regex
    words = re.findall(r"\b[a-z']+\b", feedback_lower)
    
    pain_score = 0
    fatigue_score = 0
    energy_score = 0
    
    for i, w in enumerate(words):
        # Apply simple stemming to find base form
        stemmed = stem_word(w)
        
        # Check if this word is preceded by a negation (up to 2 words before)
        is_negated = False
        for j in range(max(0, i-2), i):
            if words[j] in negations:
                is_negated = True
                break
                
        if stemmed in pain_keywords or w in pain_keywords:
            if is_negated:
                energy_score += 1
            else:
                pain_score += 1
        elif stemmed in fatigue_keywords or w in fatigue_keywords:
            if is_negated:
                energy_score += 1
            else:
                fatigue_score += 1
        elif stemmed in high_energy_keywords or w in high_energy_keywords:
            if is_negated:
                fatigue_score += 1
            else:
                energy_score += 1
                
    if pain_score > 0:
        return "pain"
    elif fatigue_score > energy_score:
        return "fatigue"
    elif energy_score > fatigue_score:
        return "high_energy"
    else:
        return "neutral"
