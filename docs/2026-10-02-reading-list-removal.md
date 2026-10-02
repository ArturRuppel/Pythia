# Reading-list removal in the touch view

Date: 2026-10-02

The Reading tab’s “On the desk” rows and active paper pages expose a labelled
“Remove from reading list” button when served live. Removal changes only
`[curation] active`, preserving the paper and its curation pass. It does not
mark a paper fully curated.

The button waits for `POST /active` acknowledgement, blocks repeat taps while
pending, and permits retry on failure. Success updates the list immediately
without a reload. The touch view and board share that update, including the
board’s existing reading-list picker. Static exports have no removal control.
