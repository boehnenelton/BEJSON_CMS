"""
Library:      lib_html3_tables.py
Family:       HTML3
Jurisdiction: ["BEJSON_LIBRARIES", "PY"]
Status:       OFFICIAL
Author:       Elton Boehnen
Version:      3.1.0 OFFICIAL
            MFDB Version: 1.31
Format_Creator: Elton Boehnen
Date:         2026-06-04
Description:  BECSS-compliant tabular data visualization engine with search and pagination.
              REMEDIATED: Implemented Field Map Indexing with Safe Get fallbacks (Phase 5.2).
"""

import json
import uuid
from typing import Dict, Optional, Any

VERSION = "3.1.0"
SCRIPT_NAME = "lib_html3_tables.py"
RELATIONAL_ID = "8f3e2d1c-4b5a-4e8a-9d6c-3f4b5a6c7d8e"
ES5_SAFE = True


COMPONENT_TEMPLATE = """
<div id="{cid}" class="c-bejson-table-wrapper">
    <div class="c-table-controls">
        <label for="{cid}_select" class="c-table-controls__label">TYPE:</label>
        <select id="{cid}_select" class="c-table-controls__select"></select>
        
        <input type="text" id="{cid}_search" class="c-table-controls__input" placeholder="Search records...">
        
        <button id="{cid}_schema_toggle" class="c-button" style="padding: 4px 12px; font-size: 0.65rem;">SCHEMA</button>
        
        <span id="{cid}_count" class="c-table-controls__count">RECORDS: 0</span>
    </div>

    <div class="c-table-container">
        <table id="{cid}_table" class="c-table" role="table">
            <thead id="{cid}_thead"></thead>
            <tbody id="{cid}_tbody"></tbody>
        </table>
    </div>

    <div class="c-pagination" id="{cid}_pagination">
        <button class="c-pagination__btn" id="{cid}_prev">PREV</button>
        <span class="c-pagination__info" id="{cid}_page_info">PAGE 1 / 1</span>
        <button class="c-pagination__btn" id="{cid}_next">NEXT</button>
    </div>

    <script>
    (function() {{
        var bejson = {bejson_data};
        var cid = "{cid}";

        function escapeHtml(unsafe) {{
            if (unsafe === null || unsafe === undefined) return "";
            return String(unsafe)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }}

        var pageSize = 20;
        var currentPage = 1;
        var currentSort = {{ column: null, direction: 'asc' }};
        
        // --- Field Map Indexing (Migration Phase 5.2) ---
        function _buildFieldIdx(doc) {{
            var fields = doc.Fields || [];
            var map = {{}};
            for (var i = 0; i < fields.length; i++) {{
                map[fields[i].name] = i;
            }}
            return map;
        }}
        
        // Internal Registry Pattern: O(1) re-resolution
        var fieldIndexMap = bejson._bejson_field_map || (bejson._bejson_field_map = _buildFieldIdx(bejson));
        
        var searchTerm = "";
        var isSchemaView = false;
        
        var selectEl = document.getElementById(cid + '_select');
        var searchEl = document.getElementById(cid + '_search');
        var schemaToggleBtn = document.getElementById(cid + '_schema_toggle');
        var theadEl = document.getElementById(cid + '_thead');
        var tbodyEl = document.getElementById(cid + '_tbody');
        var countEl = document.getElementById(cid + '_count');
        var pageInfoEl = document.getElementById(cid + '_page_info');
        var prevBtn = document.getElementById(cid + '_prev');
        var nextBtn = document.getElementById(cid + '_next');

        function renderTable() {{
            var selectedType = selectEl.value;
            var is104db = (bejson.Format_Version === '104db');
            
            if (isSchemaView) {{
                renderSchema(selectedType);
                return;
            }}
            
            searchEl.style.display = "inline-block";
            document.getElementById(cid + '_pagination').style.display = "flex";

            var filteredFields = is104db ?
                bejson.Fields.filter(function(f, i) {{ return i === 0 || f.Record_Type_Parent === selectedType; }}) :
                bejson.Fields;

            if (is104db && filteredFields.length <= 1) {{
                tbodyEl.innerHTML = '<tr><td colspan="2" style="padding:20px; color:#c00; text-align:center;">'
                    + 'WARNING: No fields declared for type \\"' + selectedType + '\\" in this schema.'
                    + '</td></tr>';
                countEl.textContent = 'Schema gap: 0 fields for type ' + selectedType;
                return;
            }}
            
            var records = is104db ? 
                bejson.Values.filter(function(r) {{ return r[0] === selectedType; }}) : 
                bejson.Values;

            // Apply Search
            if (searchTerm) {{
                var term = searchTerm.toLowerCase();
                records = records.filter(function(row) {{
                    return row.some(function(cell) {{
                        return cell !== null && String(cell).toLowerCase().indexOf(term) !== -1;
                    }});
                }});
            }}

            // Apply Sort
            if (currentSort.column) {{
                var fieldIdx = (fieldIndexMap[currentSort.column] !== undefined)
                    ? fieldIndexMap[currentSort.column]
                    : -1;
                if (fieldIdx !== -1) {{
                    records.sort(function(a, b) {{
                        var valA = a[fieldIdx], valB = b[fieldIdx];
                        if (valA === null) return 1; if (valB === null) return -1;
                        if (typeof valA === 'string') valA = valA.toLowerCase(); 
                        if (typeof valB === 'string') valB = valB.toLowerCase();
                        if (valA < valB) return currentSort.direction === 'asc' ? -1 : 1;
                        if (valA > valB) return currentSort.direction === 'asc' ? 1 : -1;
                        return 0;
                    }});
                }}
            }}

            countEl.textContent = 'RECORDS: ' + records.length;
            var totalPages = Math.ceil(records.length / pageSize) || 1;
            if (currentPage > totalPages) currentPage = totalPages;
            
            pageInfoEl.textContent = 'PAGE ' + currentPage + ' / ' + totalPages;
            prevBtn.disabled = currentPage === 1;
            nextBtn.disabled = currentPage === totalPages;

            // Render Head
            var headHtml = '<tr>';
            filteredFields.forEach(function(field) {{
                var sortIndicator = (currentSort.column === field.name) ? (currentSort.direction === 'asc' ? ' ▲' : ' ▼') : ' ↕';
                headHtml += '<th data-action="sort" data-field="' + escapeHtml(field.name) + '" style="cursor:pointer;">' + escapeHtml(field.name) + sortIndicator + '</th>';
            }});
            theadEl.innerHTML = headHtml + '</tr>';

            // Render Body (Paginated)
            var start = (currentPage - 1) * pageSize;
            var paginatedRecords = records.slice(start, start + pageSize);
            
            var bodyHtml = '';
            if (paginatedRecords.length === 0) {{
                bodyHtml = '<tr><td colspan="' + filteredFields.length + '" style="text-align:center; padding:40px; opacity:0.5;">No records found.</td></tr>';
            }} else {{
                paginatedRecords.forEach(function(record) {{
                    bodyHtml += '<tr>';
                    filteredFields.forEach(function(field) {{
                        var originalIdx = fieldIndexMap[field.name];
                        var val = record[originalIdx];
                        var displayVal = escapeHtml(val);
                        var cellClass = '';
                        
                        if (val === null || val === undefined) {{ displayVal = '<span class="c-null-val">null</span>'; }}
                        else if (typeof val === 'boolean') {{ 
                            displayVal = val ? 'TRUE' : 'FALSE'; 
                            cellClass = 'c-indicator ' + (val ? 'c-indicator--success' : 'c-indicator--fail');
                        }}
                        else if (typeof val === 'object') {{ displayVal = '<span class="u-font-mono u-fs-small">' + escapeHtml(JSON.stringify(val)) + '</span>'; }}
                        else if (val === 'SUCCESS' || val === 'OK' || val === 'PASS') cellClass = 'c-indicator c-indicator--success';
                        else if (val === 'FAIL' || val === 'ERROR') cellClass = 'c-indicator c-indicator--fail';
                        
                        bodyHtml += '<td class="' + cellClass + '">' + displayVal + '</td>';
                    }});
                    bodyHtml += '</tr>';
                }});
            }}
            tbodyEl.innerHTML = bodyHtml;
        }}


        function renderSchema(selectedType) {{
            searchEl.style.display = "none";
            document.getElementById(cid + '_pagination').style.display = "none";
            
            var fields = bejson.Fields.filter(function(f) {{
                return !f.Record_Type_Parent || f.Record_Type_Parent === selectedType;
            }});

            theadEl.innerHTML = '<tr><th style="width:40%;">Field Name</th><th style="width:30%;">Type</th><th style="width:30%;">Scope</th></tr>';
            
            var bodyHtml = '';
            fields.forEach(function(f) {{
                bodyHtml += '<tr>' +
                    '<td style="white-space:pre-wrap; word-break:break-all;"><code class="u-font-mono u-fs-small" style="color:var(--accent-color); font-weight:bold;">' + escapeHtml(f.name) + '</code></td>' +
                    '<td><span class="c-badge" style="background:var(--accent-color); color:white; padding:2px 8px; border-radius:12px; font-size:0.7rem;">' + escapeHtml(f.type) + '</span></td>' +
                    '<td style="opacity:0.7; font-size:0.8rem;">' + escapeHtml(f.Record_Type_Parent || 'GLOBAL') + '</td>' +
                '</tr>';
            }});
            tbodyEl.innerHTML = bodyHtml;
            countEl.textContent = 'FIELDS: ' + fields.length;
        }}

        selectEl.addEventListener('change', function() {{ currentPage = 1; renderTable(); }});
        searchEl.addEventListener('input', function(e) {{
            searchTerm = e.target.value;
            currentPage = 1;
            renderTable();
        }});

        // --- Centralized Event Delegation (Phase 3: Secure Logic) ---
        document.getElementById(cid).addEventListener('click', function(e) {{
            var target = e.target;
            
            // 1. Sort Toggle
            var sortBtn = target.closest('[data-action="sort"]');
            if (sortBtn) {{
                var field = sortBtn.dataset.field;
                if (currentSort.column === field) currentSort.direction = (currentSort.direction === 'asc' ? 'desc' : 'asc');
                else {{ currentSort.column = field; currentSort.direction = 'asc'; }}
                renderTable();
                return;
            }}

            // 2. Schema Toggle
            if (target.id === cid + '_schema_toggle') {{
                isSchemaView = !isSchemaView;
                target.textContent = isSchemaView ? "RECORDS" : "SCHEMA";
                renderTable();
                return;
            }}

            // 3. Pagination
            if (target.id === cid + '_prev' && currentPage > 1) {{ currentPage--; renderTable(); return; }}
            if (target.id === cid + '_next' && currentPage < Math.ceil(bejson.Values.length / pageSize)) {{ currentPage++; renderTable(); return; }}
        }});

        if (bejson.Records_Type) {{
            bejson.Records_Type.forEach(function(type) {{
                var option = document.createElement('option'); 
                option.value = type; option.textContent = type.toUpperCase(); 
                selectEl.appendChild(option);
            }});
        }} else {{
            var option = document.createElement('option'); option.value = "default"; option.textContent = "RECORDS"; selectEl.appendChild(option);
        }}
        
        renderTable();
    }})();
    </script>
</div>
"""

def html_table(doc: Dict[str, Any], container_id: Optional[str] = None) -> str:
    """
    Generate an isolated BECSS HTML table component with pagination and search.
    
    >>> html_table({"Format": "BEJSON", "Fields": [{"name": "id"}], "Values": [["1"]]})
    '<div class="c-bejson-table-wrapper">...</div>'
    """
    if not container_id:
        container_id = f"bejson_comp_{uuid.uuid4().hex[:12]}"
    
    # XSS Remediation: Secure Data Bridging (prevent </script> breakout)
    safe_json = json.dumps(doc).replace("</", "<\\/")
    return COMPONENT_TEMPLATE.format(cid=container_id, bejson_data=safe_json)
