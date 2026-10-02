# Evidence trails and a shared PDF pane

The reading app retains each visited paper/claim in a clickable trail. Back and
Forward move through it without discarding the forward portion; following a new
source after going back starts a new branch. Each tab owns its trail. Browser
history stores route snapshots, so browser Back and Forward restore the correct
screen rather than treating both gestures as a pop.

Claims with grounding links advertise “Trace sources”; borrowed claims say so.
The claim page lists the recorded source claims and papers under “Trace evidence”.
A link to a specific claim in another curated paper opens that paper's normal
reading view with the selected claim, quote and further sources at the top.
Paper notes fold below that selection. Unsharpened citations open the whole paper;
stubs explicitly say that no claim has been curated. Absence of a further link
is not presented as proof that the paper originated the finding.

PDF opens the existing resizable dock alongside the app, preserving its search,
zoom, text selection and quote highlighting. Portrait windows stack the two panes.
The pane follows the current paper or claim, including trail navigation. A source
without a local PDF clears the previous document and displays a missing-PDF message.
The Board control returns to the graph with the current paper selected and the
same PDF dock. Static builds retain evidence navigation but do not show live PDF
controls. No data or curation records are modified.


Quote text is its own PDF button in paper lists, claim pages and stance entries;
clicking it does not navigate or add a trail entry. Without a local PDF it remains
plain text. Claim text opens the claim. Revisiting any existing trail node moves
to that entry (including entries ahead of the current position), preventing
method/claim cycles from growing the trail. A source paper focused on a claim and
that claim's standalone page share one navigation identity.
