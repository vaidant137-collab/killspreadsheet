-- The relational spine.
--
-- Extraction writes here. The analyst answers by generating SQL against it,
-- rather than by reasoning over pasted document text. That single choice buys
-- deterministic arithmetic, an auditable query, charts from real rows,
-- provenance for free, and an honest answer to "where are you unsure" --
-- because unsureness is a column, not a vibe.

PRAGMA journal_mode = WAL;

-- What the buyer asked for -------------------------------------------------
CREATE TABLE IF NOT EXISTS rfx (
    rfx_id                  TEXT PRIMARY KEY,
    title                   TEXT NOT NULL,
    buyer_org               TEXT NOT NULL,
    category                TEXT NOT NULL,
    currency                TEXT NOT NULL,
    issued_date             TEXT,
    response_due            TEXT,
    award_target            TEXT,
    delivery_point          TEXT,
    required_incoterm       TEXT,
    required_payment_terms  TEXT,
    cost_of_capital_pct     REAL
);

CREATE TABLE IF NOT EXISTS rfx_line (
    line_no         INTEGER PRIMARY KEY,
    code            TEXT NOT NULL,
    description     TEXT NOT NULL,
    style           TEXT,
    ply             INTEGER,
    length_mm       INTEGER,
    width_mm        INTEGER,
    height_mm       INTEGER,
    flute           TEXT,
    liner_gsm       INTEGER,
    gsm_stack       TEXT,
    bursting_factor INTEGER,
    print_spec      TEXT,
    annual_qty      INTEGER NOT NULL,
    uom             TEXT NOT NULL,
    -- The bridge fact. NULL is meaningful: the buyer has dispatch weights for
    -- lines bought before and none for lines introduced this year, which is
    -- what makes a per-kg quote genuinely unresolvable on those lines.
    unit_weight_g   REAL,
    food_contact    INTEGER DEFAULT 0,
    requires_tooling INTEGER DEFAULT 0,
    sub_components  TEXT,
    capacity_band   TEXT
);

CREATE TABLE IF NOT EXISTS vendor (
    vendor_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    city            TEXT,
    incumbent       INTEGER DEFAULT 0,
    reply_format    TEXT,
    dimension_system TEXT,
    unit_wording    TEXT,
    currency        TEXT,
    incoterm        TEXT,
    tax_basis       TEXT,
    payment_days    INTEGER,
    validity_days   INTEGER,
    moq_pieces      INTEGER,
    fx_rate_at_quote REAL,
    freight_inr_per_shipment REAL,
    shipments_per_year INTEGER,
    early_payment_discount_pct REAL,
    early_payment_within_days  INTEGER,
    qualified       INTEGER,
    disqualified_because TEXT
);

-- What arrived, and where it came from --------------------------------------
CREATE TABLE IF NOT EXISTS source_doc (
    doc_id      TEXT PRIMARY KEY,
    vendor_id   TEXT NOT NULL REFERENCES vendor(vendor_id),
    path        TEXT NOT NULL,
    kind        TEXT NOT NULL,         -- xlsx | pdf | docx | image | email | attachment
    role        TEXT NOT NULL,         -- quote | questionnaire | evidence | brochure
    pages       INTEGER,
    bytes       INTEGER
);

-- Every extracted value carries its evidence key. Provenance is not a feature
-- bolted on later; it is a foreign key.
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    doc_id      TEXT NOT NULL REFERENCES source_doc(doc_id),
    locator     TEXT NOT NULL,          -- "p3", "Rate Working!L14", "crop:0.31,0.62,0.68,0.66"
    snippet     TEXT,
    page        INTEGER,
    bbox        TEXT
);

CREATE TABLE IF NOT EXISTS vendor_quote_line (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id       TEXT NOT NULL REFERENCES vendor(vendor_id),
    line_no         INTEGER REFERENCES rfx_line(line_no),
    vendor_label    TEXT,               -- what the VENDOR called it
    rate            REAL,               -- NULL is not zero and not no-quote
    currency        TEXT,
    basis           TEXT,
    refers_to_prior_contract INTEGER DEFAULT 0,
    excludes_sub_component   INTEGER DEFAULT 0,
    tooling_inr     REAL,
    tooling_amortised INTEGER DEFAULT 0,
    note            TEXT,
    evidence_id     TEXT REFERENCES evidence(evidence_id),
    extraction_confidence REAL DEFAULT 1.0,
    match_confidence      REAL DEFAULT 1.0,
    match_rationale TEXT
);

-- The derived layer. Nothing here was produced by a model.
CREATE TABLE IF NOT EXISTS assumption (
    key         TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    value       TEXT NOT NULL,
    unit        TEXT,
    source      TEXT NOT NULL,
    editable    INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS normalised_line (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id       TEXT NOT NULL REFERENCES vendor(vendor_id),
    line_no         INTEGER NOT NULL REFERENCES rfx_line(line_no),
    buyer_uom       TEXT NOT NULL,
    as_quoted       TEXT NOT NULL,
    landed_inr      REAL,
    state           TEXT NOT NULL,      -- extracted | derived | unresolved
    unresolved_reason TEXT,
    missing_fact    TEXT,
    assumptions_used TEXT,
    caveats         TEXT,
    base_inr        REAL,
    freight_inr     REAL,
    tooling_inr     REAL,
    discount_inr    REAL,
    npv_adjustment_inr REAL,
    evidence_id     TEXT REFERENCES evidence(evidence_id),
    extraction_confidence REAL DEFAULT 1.0,
    match_confidence      REAL DEFAULT 1.0,
    UNIQUE (vendor_id, line_no)
);

CREATE TABLE IF NOT EXISTS questionnaire_answer (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id   TEXT NOT NULL REFERENCES vendor(vendor_id),
    q_no        INTEGER NOT NULL,
    question    TEXT NOT NULL,
    answer      TEXT,
    evidence_id TEXT REFERENCES evidence(evidence_id),
    contradicted_by_evidence INTEGER DEFAULT 0,
    contradiction_note TEXT
);

-- Human-in-the-loop. A correction here is attributed and timestamped, which is
-- what makes the award memo defensible six months later.
CREATE TABLE IF NOT EXISTS review_item (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id       TEXT NOT NULL,
    line_no         INTEGER,
    field           TEXT NOT NULL,
    proposed_value  TEXT,
    confidence      REAL,
    evidence_id     TEXT REFERENCES evidence(evidence_id),
    status          TEXT DEFAULT 'open',   -- open | accepted | corrected
    corrected_value TEXT,
    reviewer        TEXT,
    reviewed_at     TEXT
);

CREATE TABLE IF NOT EXISTS injection_attempt (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id      TEXT REFERENCES source_doc(doc_id),
    vendor_id   TEXT,
    excerpt     TEXT NOT NULL,
    detected_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_nl_line   ON normalised_line(line_no);
CREATE INDEX IF NOT EXISTS ix_nl_vendor ON normalised_line(vendor_id);
CREATE INDEX IF NOT EXISTS ix_nl_state  ON normalised_line(state);
CREATE INDEX IF NOT EXISTS ix_rev_open  ON review_item(status);
