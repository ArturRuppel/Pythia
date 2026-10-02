# Library sorting

A visible Sort by selector above the library and in Filter & sort supports title
A–Z/Z–A, citation key A–Z, publication year in either direction, curation pass in
either direction, and curation-record update time in either direction. The choice
persists on the device; changing it resets pagination and returns to the top.
Equal values use citation key as a deterministic tie-break. Missing dates/years
and unknown passes appear last; stubs have pass 0.

There is no authored curation timestamp in the library schema. The update-time
option uses the curated YAML file's modification time, explicitly labelled as a
record edit (including metadata), not a curation completion date. The UI explains
that copies/restores can affect it. Stubs have no curation date. This is derived
viewer metadata only: no private YAML records are changed.
