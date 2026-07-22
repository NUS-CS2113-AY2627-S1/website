ISSUES_FOUND = [
    ('**Here are two alternative approaches to testing a software: _Scripted_ testing and _Exploratory_ testing.**',
     '**Here are two alternative approaches to testing software: _Scripted_ testing and _Exploratory_ testing.**',
     'testing/testingTypes/exploratoryVsScriptedTesting/what/text.md',
     'Fix exploratory testing wording'),  # [grammar issue] 'software' is normally uncountable in this usage.
    ('> The earlier a bug is found, the easier and cheaper to have it fixed.',
     '> The earlier a bug is found, the easier and cheaper it is to fix.',
     'testing/testingTypes/developerTesting/why/text.md',
     'Clarify early bug-fixing rule'),  # [phrasing issue] The revised wording is smoother and more direct.
    ('Such early testing software is usually, and often by necessity, done by the developers themselves i.e., developer testing.',
     'Such early testing of software is usually, and often by necessity, done by the developers themselves i.e., developer testing.',
     'testing/testingTypes/developerTesting/why/text.md',
     'Fix developer testing sentence'),  # [grammar issue] Adds the missing preposition after 'testing'.
    ('If a software product has a GUI (Graphical User Interface) component, all product-level testing (i.e., the types of testing mentioned above) need to be done using the GUI.',
     'If a software product has a GUI (Graphical User Interface) component, all product-level testing (i.e., the types of testing mentioned above) needs to be done using the GUI.',
     'testing/testAutomation/testingGuis/text.md',
     'Fix GUI testing agreement'),  # [grammar issue] 'testing' takes the singular verb 'needs'.
    ('For example, a GUI can behave differently based on whether it is minimized or maximized, in focus or out of focus, and in a high resolution display or a low resolution display.',
     'For example, a GUI can behave differently based on whether it is minimized or maximized, in focus or out of focus, and on a high-resolution display or a low-resolution display.',
     'testing/testAutomation/testingGuis/text.md',
     'Tighten GUI display wording'),  # [phrasing issue] Uses the natural preposition and hyphenates compound modifiers.
    ('  _Entry points_ refer to all places from which the method is called from the rest of the code i.e., all places where the control is handed over to the method in concern.<br>',
     '  _Entry points_ refer to all places from which the method is called by the rest of the code i.e., all places where control is handed over to the method in question.<br>',
     'testing/testCoverage/what/text.md',
     'Clarify entry point definition'),  # [phrasing issue] Removes repeated 'from' wording and uses a more natural phrase.
    ('**_Test-Driven Development(TDD)_ advocates writing the tests before writing the SUT, while evolving functionality and tests in small increments**.',
     '**_Test-Driven Development (TDD)_ advocates writing the tests before writing the SUT, while evolving functionality and tests in small increments**.',
     'testing/tdd/what/text.md',
     'Add space before TDD acronym'),  # [punctuation issue] Adds the missing space before the parenthetical acronym.
]
