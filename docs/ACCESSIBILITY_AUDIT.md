# Accessibility audit

Audit target: FiniSpeak deployment-ready web application  
Standard used: WCAG 2.2 Level AA  
Method: source inspection, keyboard-flow review, semantic regression tests, and manual interaction review.

## Implemented controls

- A skip link moves focus to the main content region.
- Every primary workflow is keyboard operable and has a visible focus indicator.
- Tabs implement the tablist, tab, and tabpanel pattern with arrow-key navigation.
- Dialogs expose accessible names, descriptions where applicable, focus containment, Escape dismissal, focus restoration, and inert background content.
- Call microphone and camera controls expose their pressed state.
- Live status updates use polite status regions; transcripts use named log regions.
- Forms use programmatic labels, grouped checkboxes, instructions, and error/status announcements.
- UI motion is effectively disabled when the operating system requests reduced motion.
- Color is not the only indicator for verification, availability, validation, or call state.

## Automated regression gate

Run `python -m unittest tests.test_accessibility`. The test validates document language, skip navigation, label targets, dialog naming/state, call toggle state, and transcript log semantics.

## Manual release checks

Before each release, complete keyboard-only passes at 200% zoom and test the main flows with VoiceOver/Safari and NVDA/Chrome. Record browser, assistive-technology version, findings, owner, and resolution here.

## Certification boundary

This is an internal conformance review, not an independent accessibility certification. Obtain a third-party audit before making a contractual claim of WCAG 2.2 AA conformance.
