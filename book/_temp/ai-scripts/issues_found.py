ISSUES_FOUND = [
    ('The component that detects it is the _emitter_; components that react are _consumers_.',
     'The component that emits an event is the _emitter_; components that react are _consumers_.',
     'architecture/architecturalStyles/eventDriven/what/text.md',
     'Define the event emitter precisely'),  # [phrasing] The pronoun `it` has no clear antecedent, and an emitter emits rather than merely detects an event.
    ('**A good architecture contains many kinds of change, but not every kind:**',
     '**A good architecture contains the effects of many kinds of change, but not every kind:**',
     'architecture/introduction/components/q-list-whichComponentChanges.md',
     'Clarify what architecture contains'),  # [phrasing] An architecture contains the effects of a change; it does not contain the change itself.
    ('%%Notation used in this diagram and the next: a dashed arrow is the path along which events travel, each oval is one event, and the small red arrows show events in flight along that path.%%',
     '%%Notation used in this diagram and the next: a dashed arrow is the path along which events travel, each oval is one event, and the small red arrows show their direction of travel.%%',
     'architecture/architecturalStyles/eventDriven/what/text.md',
     'Clarify event diagram notation'),  # [phrasing] The ovals show the events; the red arrows show their direction rather than the events themselves.
    ('1. `Storage` mainly — the others asked it to save and never knew the format, assuming its interface still fits.',
     '1. `Storage` mainly — the others ask it to save and do not know the format, assuming its interface still fits.',
     'architecture/introduction/components/q-list-whichComponentChanges.md',
     'Keep exercise answer in present tense'),  # [grammar] The hypothetical answer should use the same present tense as the surrounding exercise.
    ('(a)(b)',
     '(a), (b)',
     'architecture/introduction/what/q-tick-correctStatement.md',
     'Punctuate multiple answer labels'),  # [punctuation] A comma and space are needed between the two answer labels.
]
