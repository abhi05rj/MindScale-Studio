"""Deterministic editorial patterns and quality safeguards."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ContentAnglePattern:
    name: str
    title: str
    hook: str
    angle: str
    opening: str
    escalation: str
    takeaway: str
    visual_direction: str


@dataclass(frozen=True)
class EditorialVariant:
    title: str
    hook: str


CONTENT_ANGLE_PATTERNS = (
    ContentAnglePattern(
        name="scale/comparison",
        title="See {topic} at True Scale: A Comparison You Can Picture",
        hook="One familiar comparison makes the true scale of {subject} feel completely different.",
        angle="Scale/comparison: anchor {subject} to a familiar human-sized object, then zoom through three measurable jumps.",
        opening="Open with {subject} beside one familiar object the audience instantly recognizes.",
        escalation="Move through three scale jumps, keeping the original object visible as an anchor.",
        takeaway="End with one ratio that makes the scale of {subject} easy to remember and share.",
        visual_direction="Three-stage scale ladder for {subject}; familiar object in foreground, repeated size anchor, dramatic zoom-out, clear depth and measurable contrast",
    ),
    ContentAnglePattern(
        name="counterintuitive fact",
        title="One Fact About {topic} That Sounds Wrong—but Isn't",
        hook="The most useful fact about {subject} initially feels like it should be impossible.",
        angle="Counterintuitive fact: contrast the intuitive guess about {subject} with the evidence that overturns it.",
        opening="Show the common assumption about {subject} as a simple visual prediction.",
        escalation="Reveal the contradictory evidence in two clear steps, then explain why intuition fails.",
        takeaway="Close with the corrected mental model viewers will want to repeat to someone else.",
        visual_direction="Split-screen misconception versus reality for {subject}; strong central contrast, one visual reveal, evidence markers, editorial before-and-after composition",
    ),
    ContentAnglePattern(
        name="what-if scenario",
        title="What If We Experienced {topic} at 10× Scale?",
        hook="Changing one condition turns {subject} into a thought experiment with surprising consequences.",
        angle="What-if scenario: change one rule of {subject}, then trace three consequences from personal to planetary scale.",
        opening="Establish normal {subject} and clearly identify the single rule that will change.",
        escalation="Follow three cause-and-effect consequences, increasing the stakes at each step.",
        takeaway="Return to reality and show what the scenario reveals about how {subject} actually works.",
        visual_direction="Cause-and-effect triptych for {subject}; normal baseline on left, altered 10× world at center, cascading consequences on right, cinematic visual continuity",
    ),
    ContentAnglePattern(
        name="hidden mechanism",
        title="The Hidden Chain Reaction Shaping {topic}",
        hook="What looks simple on the surface of {subject} depends on an invisible sequence underneath.",
        angle="Hidden mechanism: peel back the visible surface of {subject} to expose the linked process underneath.",
        opening="Begin with the familiar visible result of {subject} before revealing what is hidden.",
        escalation="Use a cutaway sequence to connect trigger, mechanism, and visible outcome.",
        takeaway="Finish by reconnecting the hidden mechanism to an everyday observation.",
        visual_direction="Layered cutaway of {subject}; visible surface above, hidden mechanism below, luminous directional flow, three linked stages, precise focal hierarchy",
    ),
    ContentAnglePattern(
        name="timeline/transformation",
        title="5 Turning Points That Shaped {topic}",
        hook="Five turning points reveal how {subject} became what we recognize today.",
        angle="Timeline/transformation: compress the evolution of {subject} into five decisive visual turning points.",
        opening="Start at the earliest recognizable state of {subject} with a clear time marker.",
        escalation="Advance through five transformations, making the change between stages visually explicit.",
        takeaway="End in the present with one clue about what may change next.",
        visual_direction="Five-panel transformation timeline for {subject}; left-to-right progression, consistent subject silhouette, changing environment, distinct era cues, strong final-state emphasis",
    ),
    ContentAnglePattern(
        name="pattern discovery",
        title="A Pattern in {topic} Hiding in Plain Sight",
        hook="Once you notice this repeating pattern in {subject}, ordinary scenes become evidence.",
        angle="Pattern discovery: connect three everyday examples of {subject} to the same underlying rule.",
        opening="Show three apparently unrelated scenes where {subject} appears.",
        escalation="Overlay the shared pattern so the connection becomes visually undeniable.",
        takeaway="Give viewers one observation prompt they can use to spot the pattern themselves.",
        visual_direction="Three everyday vignettes linked by one repeating geometry for {subject}; subtle-to-bright pattern reveal, unified color cue, discovery-focused composition",
    ),
    ContentAnglePattern(
        name="boundary/threshold",
        title="Where Does {topic} End—and Something Else Begin?",
        hook="The boundary around {subject} is less like a line and more like a revealing transition zone.",
        angle="Boundary/threshold: investigate where {subject} changes category and why the edge is scientifically useful.",
        opening="Present two obvious extremes with {subject} positioned between them.",
        escalation="Zoom into the transition zone and compare three signals that change at different rates.",
        takeaway="End with a practical definition that is more precise than the original either-or choice.",
        visual_direction="Gradient threshold map for {subject}; two contrasting extremes, magnified transition zone, three changing signals, elegant scientific cross-section",
    ),
)


TOPIC_DISPLAY_NAMES = {
    "universe": "the Universe",
    "space": "Outer Space",
    "time": "Time",
    "human perspective": "Human Perception",
    "ocean": "the Ocean",
    "brain": "the Human Brain",
    "nature": "Nature",
}

TOPIC_SENTENCE_NAMES = {
    "universe": "the observable universe",
    "space": "the vacuum of space",
    "time": "time",
    "human perspective": "visual perception",
    "ocean": "deep-ocean circulation",
    "brain": "the brain's attention system",
    "nature": "a forest ecosystem",
}


TOPIC_PATTERN_OVERRIDES = {
    ("human perspective", "hidden mechanism"): EditorialVariant(
        "Your Brain Edits Reality Before You Ever See It",
        "Every glance is compressed, corrected, and partly invented before it reaches conscious awareness.",
    ),
    ("human perspective", "pattern discovery"): EditorialVariant(
        "Why Two People Can Look at the Same Scene and Notice Different Worlds",
        "Attention quietly decides which details become your reality—and which ones disappear.",
    ),
    ("ocean", "timeline/transformation"): EditorialVariant(
        "How One Drop Can Spend 1,000 Years Crossing the Ocean",
        "A single parcel of seawater can circle the planet on a journey longer than many civilizations have existed.",
    ),
    ("ocean", "hidden mechanism"): EditorialVariant(
        "The Underwater Conveyor Belt That Regulates Earth’s Climate",
        "Far below the waves, temperature and salt drive a planetary current that redistributes heat for centuries.",
    ),
    ("brain", "pattern discovery"): EditorialVariant(
        "Your Brain Deletes Details Every Time You Look Away",
        "The gaps in your attention feel invisible because your brain replaces missing detail with a convincing guess.",
    ),
    ("nature", "boundary/threshold"): EditorialVariant(
        "The Invisible Threshold Between a Tree Stand and a Living Forest",
        "A collection of trees becomes a resilient forest only when hidden relationships begin recycling water, nutrients, and life.",
    ),
    ("nature", "scale/comparison"): EditorialVariant(
        "A Teaspoon of Forest Soil Can Hold More Life Than a City Block",
        "The smallest patch of healthy soil can contain an ecosystem dense enough to change how you see the ground beneath you.",
    ),
    ("universe", "scale/comparison"): EditorialVariant(
        "The Observable Universe Is 93 Billion Light-Years Wide—So Why Is It 13.8 Billion Years Old?",
        "Cosmic expansion makes the universe far larger than a simple light-travel calculation suggests.",
    ),
    ("universe", "boundary/threshold"): EditorialVariant(
        "The Edge of the Observable Universe Isn’t a Wall",
        "Our cosmic horizon marks the oldest light we can receive—not the place where the universe physically ends.",
    ),
    ("space", "counterintuitive fact"): EditorialVariant(
        "Space Isn’t Completely Silent—It’s Full of Waves We Can’t Hear",
        "Vacuum blocks ordinary sound, yet pressure waves still move through plasma, gas, and magnetic fields across space.",
    ),
    ("space", "pattern discovery"): EditorialVariant(
        "The Same Spiral Pattern Connects Hurricanes and Galaxies",
        "Structures separated by trillions of kilometers can echo the same geometry without sharing the same cause.",
    ),
    ("time", "what-if scenario"): EditorialVariant(
        "If Time Ran 10× Faster, Your Body Would Notice First",
        "A faster clock would reshape sleep, healing, memory, and aging before society could adjust its schedule.",
    ),
    ("time", "scale/comparison"): EditorialVariant(
        "Your Brain Can Stretch a Second Without Changing the Clock",
        "Fear, novelty, and attention can make equal moments feel radically different in memory.",
    ),
}


TOPIC_REWRITE_OVERRIDES = {
    ("brain", "pattern discovery"): EditorialVariant(
        "Look Away for 1 Second—Your Brain Rebuilds the Scene",
        "When attention breaks, the brain fills the missing moment with its best prediction rather than a faithful recording.",
    ),
}


GENERIC_TITLE_PATTERNS = (
    re.compile(r"^what makes .+ so fascinating\??$", re.IGNORECASE),
    re.compile(r"^a visual guide to .+$", re.IGNORECASE),
    re.compile(r"^understanding .+ at a glance$", re.IGNORECASE),
    re.compile(r"^.+: the big picture$", re.IGNORECASE),
    re.compile(r"^a new way to see .+$", re.IGNORECASE),
)


def is_generic_title(title: str) -> bool:
    clean = " ".join(title.split())
    return any(pattern.match(clean) for pattern in GENERIC_TITLE_PATTERNS)


def pattern_for(topic: str, seed: int = 0) -> ContentAnglePattern:
    normalized = topic.strip().casefold()
    deterministic = sum((index + 1) * ord(character) for index, character in enumerate(normalized))
    return CONTENT_ANGLE_PATTERNS[(deterministic + seed) % len(CONTENT_ANGLE_PATTERNS)]


def pattern_for_angle(angle: str) -> ContentAnglePattern | None:
    angle_name = angle.split(":", 1)[0].strip().casefold()
    return next(
        (pattern for pattern in CONTENT_ANGLE_PATTERNS if pattern.name == angle_name),
        None,
    )


def display_topic(topic: str) -> str:
    clean = topic.strip()
    return TOPIC_DISPLAY_NAMES.get(clean.casefold(), clean.title())


def has_editorial_profile(topic: str) -> bool:
    return topic.strip().casefold() in TOPIC_SENTENCE_NAMES


def format_pattern_text(template: str, topic: str) -> str:
    clean = topic.strip()
    subject = TOPIC_SENTENCE_NAMES.get(clean.casefold(), clean.casefold())
    return template.format(topic=display_topic(clean), subject=subject)


def editorial_variant(topic: str, pattern: ContentAnglePattern) -> EditorialVariant:
    override = TOPIC_PATTERN_OVERRIDES.get((topic.strip().casefold(), pattern.name))
    if override:
        return override
    return EditorialVariant(
        title=format_pattern_text(pattern.title, topic),
        hook=format_pattern_text(pattern.hook, topic),
    )


def rewrite_editorial_variant(
    topic: str, pattern: ContentAnglePattern
) -> EditorialVariant | None:
    return TOPIC_REWRITE_OVERRIDES.get((topic.strip().casefold(), pattern.name))


def rewrite_generic_title(title: str, topic: str, seed: int = 0) -> str:
    if not is_generic_title(title):
        return title.strip()
    return format_pattern_text(pattern_for(topic, seed).title, topic)
