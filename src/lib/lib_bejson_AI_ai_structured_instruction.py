"""
Library:        lib_bejson_AI_ai_structured_instruction.py
Family:         AI
Description:    "Structured-Instruction" half of a matched instruction/
                 reception pair. This library's only job is to hand back
                 instruction text telling an LLM how to format its output
                 in a specific, machine-parseable way -- it never sends
                 anything to a model itself (that's the caller's job, via
                 ai_dispatch.py or otherwise) and it has no opinion about
                 what happens to the model's response afterward. Its
                 matching partner, lib_bejson_AI_ai_structured_reception.py,
                 is the only thing that knows how to parse output produced
                 under a given function's instructions -- the two must be
                 read together; changing one format without a matching
                 change to its partner breaks the pair silently.

                 structured_instruction_list() is the generic case: a
                 simple, LLM-reliable delimited block format for "generate
                 N items with these fields" (the concept's own worked
                 example -- five ideas the user checks boxes on and moves
                 to another list). Deliberately not JSON: a plain
                 [ITEM]...[/ITEM] block format is far more likely to come
                 back well-formed from smaller/free-tier models than JSON
                 is, which matters given how many of this project's wired
                 providers are free-tier.

                 structured_instruction_chunker_project() is the specific
                 case this file was asked to add: it returns Elton's own
                 tuned BEJSON-104db "chunker" instruction set verbatim,
                 asking an LLM to emit an entire project (files + a
                 project-meta row) as one 104db document. The text is
                 reproduced exactly as provided -- including its literal
                 backslash-escaped quotes in the prose sections -- since
                 it's a precise, presumably-already-tested prompt artifact;
                 rewording or "fixing" it risks changing model behavior
                 that was tuned deliberately.
Version:        1.0.0
Date:           2026-09-27
Author:         Elton Boehnen
Contact:        eltonboehnen@gmail.com | boehnenelton2024.pages.dev | github.com/boehnenelton
Format_Creator: Elton Boehnen
RELATIONAL_ID:  3e9a7c15-6b2d-4f81-9e3a-7c5d1b8f4a29
Release_Version: 300

Changelog:
  1.0.0 (2026-09-27) -- Initial creation. structured_instruction_list()
        is this pass's generic function (from the Structured-Instruction/
        Structured-Reception design discussion); structured_instruction_
        chunker_project() is the second function this pass was asked to
        add, sourced verbatim from
        _INSTRUCTIONS__CLI_Chunker_LLM_Output.md.
"""

import logging

_logger = logging.getLogger(__name__)


# ── Generic: N items with named fields, as delimited blocks ─────────────────

def structured_instruction_list(fields: list, count: int = None, block_name: str = "ITEM") -> str:
    """
    Returns instruction text asking the model to emit a series of
    [ITEM]...[/ITEM] blocks (or block_name if overridden), one "field:
    value" line per field, in the given order. Deliberately plain-text and
    delimiter-based rather than JSON -- far more forgiving of a smaller or
    free-tier model's tendency to drift on strict syntax.

    fields: ordered list of field names, e.g. ["title", "description"].
    count: if given, tells the model exactly how many items to produce;
    if None, the model decides how many.
    block_name: the delimiter tag, in case a caller wants something more
    specific than the generic "ITEM" (e.g. "IDEA", "TASK").

    The matching parser is
    lib_bejson_AI_ai_structured_reception.structured_reception_parse_list().
    """
    count_line = f"Produce exactly {count} {block_name} blocks." if count else f"Produce as many {block_name} blocks as appropriate."
    field_lines = "\n".join(f"{f}: <{f} value, one line, no line breaks>" for f in fields)
    return (
        f"Format your response as a series of [{block_name}]...[/{block_name}] "
        f"blocks and nothing else -- no preamble, no explanation, no text "
        f"outside the blocks. {count_line} Each block must contain exactly "
        f"these fields, one per line, in this order:\n\n"
        f"[{block_name}]\n{field_lines}\n[/{block_name}]\n\n"
        f"Repeat that block structure for each item. Do not add extra "
        f"fields, extra commentary, or markdown formatting around the "
        f"blocks."
    )


# ── Specific: full project as BEJSON 104db (Elton's tuned chunker prompt) ───

_CHUNKER_PROJECT_INSTRUCTION = r"""[SYSTEM_Bypass_Preambles]: TRUE
[Output_Mode]: RAW_JSON_ONLY
[Character_Limit]: 65536
[Silence_Mandate]: ABSOLUTE

# YOU ARE A MACHINE. YOU ARE A BEJSON 104DB GENERATOR MATCHING THE CANONICAL CLI CHUNKER SPECIFICATIONS.
# YOU DO NOT HAVE A BRAIN. YOU DO NOT HAVE AN OPINION.
# YOU DO NOT EXPLAIN. YOU DO NOT TALK.

## BEJSON IS LIKE A SPREADSHEET:
To understand BEJSON 104db, think of it as a flat spreadsheet:
1. "Fields" are the column headers for the entire spreadsheet. Every column is declared in this array with a specific data type.
2. "Values" are the rows of records. Every row in "Values" MUST contain the exact same number of elements as the "Fields" array. They must align positionally, field-for-field. If a value is missing or not applicable, you MUST populate it with "null" to maintain positional integrity.
3. "Record_Type_Parent" acts as a discriminator. It behaves like multiple spreadsheet pages crammed into a single master sheet. Since 104db stores different record types (like "ProjectMeta" and "FileContent") in one table, "Record_Type_Parent" at index 0 signifies which record type (spreadsheet page) the current row belongs to.
4. Non-applicable fields for a row's active "Record_Type_Parent" must be padded with "null" so that the record matches the exact length of the defined column headers.

## BEJSON 104DB CRASH COURSE STRUCTURE:
- Format: Must be exactly "BEJSON".
- Format_Creator: Must be precisely "Elton Boehnen".
- Format_Version: Must be exactly "104db".
- Records_Type: Must contain two or more unique entity names representing spreadsheet pages. Usually ["ProjectMeta", "FileContent"].
- Top-level keys: Strictly limited to format metadata. No custom top-level keys are allowed under 104db rules.
- The very first field MUST be: {"name": "Record_Type_Parent", "type": "string"}.
- Every other field must specify its "Record_Type_Parent" association.
- Value position 0 in every row must match one of the entries in Records_Type.

## SCHEMA EXPECTATION:
Positional Schema Fields:
- [0] Record_Type_Parent (string)
- [1] project_name (string, Record_Type_Parent: ProjectMeta)
- [2] version (string, Record_Type_Parent: ProjectMeta)
- [3] root_path (string, Record_Type_Parent: ProjectMeta)
- [4] file_path (string, Record_Type_Parent: FileContent)
- [5] file_name (string, Record_Type_Parent: FileContent)
- [6] content (string, Record_Type_Parent: FileContent)
- [7] is_binary (boolean, Record_Type_Parent: FileContent)

Values mapping:
- ProjectMeta row: ["ProjectMeta", project_name, version, root_path, null, null, null, null]
- FileContent row: ["FileContent", null, null, null, file_path, file_name, content, is_binary]

## FEW_SHOT_EXAMPLE:
USER: HelloWorld project with main.py
MODEL: {
  "Format": "BEJSON",
  "Format_Version": "104db",
  "Format_Creator": "Elton Boehnen",
  "Records_Type": ["ProjectMeta", "FileContent"],
  "Fields": [
    {"name": "Record_Type_Parent", "type": "string"},
    {"name": "project_name", "type": "string", "Record_Type_Parent": "ProjectMeta"},
    {"name": "version", "type": "string", "Record_Type_Parent": "ProjectMeta"},
    {"name": "root_path", "type": "string", "Record_Type_Parent": "ProjectMeta"},
    {"name": "file_path", "type": "string", "Record_Type_Parent": "FileContent"},
    {"name": "file_name", "type": "string", "Record_Type_Parent": "FileContent"},
    {"name": "content", "type": "string", "Record_Type_Parent": "FileContent"},
    {"name": "is_binary", "type": "boolean", "Record_Type_Parent": "FileContent"}
  ],
  "Values": [
    ["ProjectMeta", "HelloWorld", "1.0.0", "/", null, null, null, null],
    ["FileContent", null, null, null, "main.py", "main.py", "print("hello")", false]
  ]
}

## EXECUTE_NOW
"""


def structured_instruction_chunker_project() -> str:
    """
    Returns Elton's tuned BEJSON-104db "chunker" instruction set verbatim
    (see _INSTRUCTIONS__CLI_Chunker_LLM_Output.md) -- prepend this to a
    prompt describing the project you want generated (e.g. "HelloWorld
    project with main.py") and dispatch it via ai_dispatch.py like any
    other call.

    The matching parser is lib_bejson_AI_ai_structured_reception.
    structured_reception_rebuild_project(), which expects exactly the
    schema this instruction text specifies (Record_Type_Parent-
    discriminated ProjectMeta/FileContent rows) and will write the
    resulting project back out to real files on disk.
    """
    return _CHUNKER_PROJECT_INSTRUCTION
