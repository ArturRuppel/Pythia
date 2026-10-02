# Claim structure in the reading app

Paper claims and the Topics tab's broad claims use nested family boxes, following
the old synthesis-band design. All statements remain visible at rest. A broader
claim contains its narrower claims; a paper claim also contains its local
supporting claims, with an explicit relationship label distinguishing the two.
Questions and methods retain their own sections; citations remain in Trace evidence.

Each claim has one full rendering. Authored generalization order chooses its host
first; local grounding supplies a host otherwise. Additional parents get a shared
claim reference that opens the same claim detail. A defensive cycle check keeps
all nodes visible without recursive loops. Independent claims remain root cards.
Families are rendered whole, so pagination cannot sever a claim from its parent.

Claim text opens its detail, and quote text opens the PDF as before. The nested
structure uses recorded edges only and adds no inferred relationships.
