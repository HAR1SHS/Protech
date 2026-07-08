import csv
import json
import os
import re

csv_file = "../data/Meter-Utility master/McDonalds_SD_Meter_Reference_Data(Overview).csv"

# 1. Parse the CSV
data = []
with open(csv_file, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row.get('UtilityName'):  # skip empty rows
            data.append({
                "utility": row.get('UtilityName', '').strip(),
                "group": row.get('UtilityGroup', '').strip(),
                "metric": row.get('LineConnected', '').strip(),
                "uomName": row.get('UomName', '').strip(),
                "uomScale": row.get('UomScale', '').strip(),
                "description": row.get('Description', '').strip(),
                "sampleValues": row.get('SampleValues', '').strip(),
                "formula": row.get('Formula', '').strip()
            })

json_data = json.dumps(data)

# 2. Generate Protech_Meter_Utility_Master.html
html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meter-Utility Master Dictionary</title>
    <style>
        body, html {{
            margin: 0;
            padding: 0;
            height: 100%;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f8fafc;
            color: #0f172a;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 40px 20px;
            display: flex;
            flex-direction: column;
            gap: 25px;
        }}

        h1 {{
            color: #0f172a;
            margin: 0;
            font-size: 2rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 1px;
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        
        /* Filters */
        .filters {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            background: #ffffff;
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 4px 10px rgba(15, 23, 42, 0.03);
            align-items: center;
        }}

        .filter-btn {{
            background: #f1f5f9;
            border: 1px solid #cbd5e1;
            color: #475569;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.95rem;
            transition: all 0.3s;
        }}

        .filter-btn:hover {{
            background: #e2e8f0;
            transform: translateY(-1px);
        }}

        .filter-btn.active {{
            background: #0ea5e9;
            color: white;
            border-color: #0ea5e9;
            box-shadow: 0 4px 10px rgba(14, 165, 233, 0.3);
        }}

        .search-box {{
            margin-left: auto;
            padding: 10px 15px;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            width: 300px;
            font-size: 1rem;
            outline: none;
            transition: border-color 0.3s;
        }}
        
        .search-box:focus {{
            border-color: #0ea5e9;
            box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.1);
        }}

        /* Grid */
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 20px;
        }}

        /* Card */
        .card {{
            background: #ffffff;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            border-left: 5px solid #64748b;
            box-shadow: 0 4px 6px rgba(15, 23, 42, 0.03);
            overflow: hidden;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            cursor: pointer;
            display: flex;
            flex-direction: column;
        }}

        .card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 12px 25px rgba(15, 23, 42, 0.08);
            border-color: #cbd5e1;
        }}

        .card-header {{
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .metric-title {{
            font-size: 1.1rem;
            font-weight: 700;
            color: #1e293b;
            margin: 0;
        }}

        .utility-badge {{
            font-size: 0.75rem;
            font-weight: 800;
            padding: 4px 8px;
            border-radius: 6px;
            background: #f1f5f9;
            color: #475569;
            text-transform: uppercase;
        }}

        .card-body {{
            padding: 0 20px;
            max-height: 0;
            opacity: 0;
            overflow: hidden;
            transition: all 0.4s ease;
            background: #f8fafc;
            border-top: 1px solid transparent;
        }}

        .card.expanded .card-body {{
            padding: 20px;
            max-height: 500px;
            opacity: 1;
            border-top-color: #e2e8f0;
        }}

        .card.expanded {{
            border-left-width: 8px;
        }}

        .meta-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
        }}
        
        .meta-item {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .meta-label {{
            font-size: 0.75rem;
            color: #64748b;
            font-weight: 700;
            text-transform: uppercase;
        }}

        .meta-value {{
            font-size: 0.95rem;
            font-weight: 600;
            color: #0ea5e9;
            background: #e0f2fe;
            padding: 4px 10px;
            border-radius: 6px;
            display: inline-block;
        }}

        .desc-text {{
            font-size: 0.95rem;
            color: #334155;
            line-height: 1.5;
            margin: 0 0 15px 0;
        }}
        
        .samples-box {{
            background: #1e293b;
            color: #10b981;
            padding: 10px 15px;
            border-radius: 8px;
            font-family: monospace;
            font-size: 0.85rem;
            overflow-x: auto;
        }}
        
        /* Utility Colors */
        .color-eb {{ border-left-color: #eab308; }}
        .badge-eb {{ background: #fef08a; color: #854d0e; }}
        
        .color-dg {{ border-left-color: #f97316; }}
        .badge-dg {{ background: #ffedd5; color: #9a3412; }}
        
        .color-hvac {{ border-left-color: #3b82f6; }}
        .badge-hvac {{ background: #dbeafe; color: #1e40af; }}
        
        .color-kitchen {{ border-left-color: #22c55e; }}
        .badge-kitchen {{ background: #dcfce3; color: #166534; }}
        
        .color-water {{ border-left-color: #06b6d4; }}
        .badge-water {{ background: #cffafe; color: #155e75; }}
        
        .color-lpg {{ border-left-color: #ef4444; }}
        .badge-lpg {{ background: #fee2e2; color: #991b1b; }}
        
        .color-munter {{ border-left-color: #8b5cf6; }}
        .badge-munter {{ background: #ede9fe; color: #5b21b6; }}
        
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Meter-Utility Data Dictionary</h1>
        
        <div class="filters">
            <button class="filter-btn active" data-filter="all">All Utilities</button>
            <button class="filter-btn" data-filter="EB">EB (Grid)</button>
            <button class="filter-btn" data-filter="DG">DG (Generator)</button>
            <button class="filter-btn" data-filter="HVAC">HVAC</button>
            <button class="filter-btn" data-filter="Kitchen_Equip">Kitchen</button>
            <button class="filter-btn" data-filter="LPG">LPG</button>
            <button class="filter-btn" data-filter="Water">Water</button>
            <button class="filter-btn" data-filter="Munter Ctrl">Munter Ctrl</button>
            
            <input type="text" id="search" class="search-box" placeholder="Search metrics or definitions...">
        </div>
        
        <div class="grid" id="grid">
            <!-- Cards will be injected here -->
        </div>
    </div>

    <script>
        const rawData = {json_data};
        
        const grid = document.getElementById('grid');
        const searchBox = document.getElementById('search');
        const filterBtns = document.querySelectorAll('.filter-btn');
        
        let currentFilter = 'all';
        let currentSearch = '';

        function getUtilityColorClass(utility) {{
            const u = utility.toLowerCase();
            if (u.includes('eb')) return 'color-eb';
            if (u.includes('dg')) return 'color-dg';
            if (u.includes('hvac')) return 'color-hvac';
            if (u.includes('kitchen')) return 'color-kitchen';
            if (u.includes('water')) return 'color-water';
            if (u.includes('lpg')) return 'color-lpg';
            if (u.includes('munter')) return 'color-munter';
            return '';
        }}

        function getBadgeColorClass(utility) {{
            const u = utility.toLowerCase();
            if (u.includes('eb')) return 'badge-eb';
            if (u.includes('dg')) return 'badge-dg';
            if (u.includes('hvac')) return 'badge-hvac';
            if (u.includes('kitchen')) return 'badge-kitchen';
            if (u.includes('water')) return 'badge-water';
            if (u.includes('lpg')) return 'badge-lpg';
            if (u.includes('munter')) return 'badge-munter';
            return '';
        }}

        function renderCards() {{
            grid.innerHTML = '';
            
            const filteredData = rawData.filter(item => {{
                const matchesFilter = currentFilter === 'all' || item.utility.includes(currentFilter);
                const searchLower = currentSearch.toLowerCase();
                const matchesSearch = item.metric.toLowerCase().includes(searchLower) || 
                                      item.description.toLowerCase().includes(searchLower) ||
                                      item.utility.toLowerCase().includes(searchLower);
                return matchesFilter && matchesSearch;
            }});

            filteredData.forEach((item, index) => {{
                const card = document.createElement('div');
                card.className = `card ${{getUtilityColorClass(item.utility)}}`;
                
                // Clean up description (remove the "Utility | Metric -" prefix if present)
                let cleanDesc = item.description;
                if (cleanDesc.includes('—')) {{
                    cleanDesc = cleanDesc.split('—')[1].trim();
                }} else if (cleanDesc.includes('-')) {{
                    cleanDesc = cleanDesc.split('-')[1].trim();
                }}

                card.innerHTML = `
                    <div class="card-header">
                        <h3 class="metric-title">${{item.metric}}</h3>
                        <span class="utility-badge ${{getBadgeColorClass(item.utility)}}">${{item.utility}}</span>
                    </div>
                    <div class="card-body">
                        <div class="meta-row">
                            <div class="meta-item">
                                <span class="meta-label">Type / UOM</span>
                                <span class="meta-value">${{item.uomName}} (${{item.uomScale}})</span>
                            </div>
                            ${{item.group ? `<div class="meta-item"><span class="meta-label">Group</span><span class="meta-value" style="background:#f1f5f9; color:#475569;">${{item.group}}</span></div>` : ''}}
                        </div>
                        <p class="desc-text">${{cleanDesc || 'No description provided.'}}</p>
                        ${{item.sampleValues ? `
                        <div class="meta-label" style="margin-bottom:6px;">Sample Payload Values</div>
                        <div class="samples-box">${{item.sampleValues}}</div>
                        ` : ''}}
                    </div>
                `;
                
                // Toggle expansion
                card.addEventListener('click', () => {{
                    const isExpanded = card.classList.contains('expanded');
                    // Collapse all others
                    document.querySelectorAll('.card').forEach(c => c.classList.remove('expanded'));
                    if (!isExpanded) {{
                        card.classList.add('expanded');
                    }}
                }});

                grid.appendChild(card);
            }});
        }}

        // Event Listeners
        filterBtns.forEach(btn => {{
            btn.addEventListener('click', (e) => {{
                filterBtns.forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                currentFilter = e.target.getAttribute('data-filter');
                renderCards();
            }});
        }});

        searchBox.addEventListener('input', (e) => {{
            currentSearch = e.target.value;
            renderCards();
        }});

        // Initial Render
        renderCards();
    </script>
</body>
</html>
"""

with open('Protech_Meter_Utility_Master.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

print("Created Protech_Meter_Utility_Master.html successfully!")

# 3. Update Protech_Presentation.html
presentation_path = 'Protech_Presentation.html'
with open(presentation_path, 'r', encoding='utf-8') as f:
    pres_content = f.read()

# Add button
if 'Meter-Utility Dictionary' not in pres_content:
    btn_target = '<button class="tab" onclick="switchTab(\'databricks\', this)">\n            Databricks Medallion\n        </button>'
    new_btn = btn_target + '\n        <button class="tab" onclick="switchTab(\'dictionary\', this)">\n            Meter-Utility Dictionary\n        </button>'
    pres_content = pres_content.replace(btn_target, new_btn)

# Add iframe
if 'frame-dictionary' not in pres_content:
    iframe_target = '<iframe id="frame-databricks" src="Protech_Databricks_Architecture.html"></iframe>'
    new_iframe = iframe_target + '\n        <iframe id="frame-dictionary" src="Protech_Meter_Utility_Master.html"></iframe>'
    pres_content = pres_content.replace(iframe_target, new_iframe)

with open(presentation_path, 'w', encoding='utf-8') as f:
    f.write(pres_content)

print("Updated Protech_Presentation.html successfully!")

# 4. We will also recreate combine_presentation.py to generate index.html 
# since it's missing but expected by the user architecture.
combine_script = '''import os
import re

print("Building index.html...")

with open("Protech_Presentation.html", "r", encoding="utf-8") as f:
    content = f.read()

# Find all iframes with src
iframe_pattern = re.compile(r'<iframe id="([^"]+)" src="([^"]+)"(.*?)></iframe>')

def replacer(match):
    frame_id = match.group(1)
    src_file = match.group(2)
    extras = match.group(3)
    
    # Read the target file
    try:
        with open(src_file, "r", encoding="utf-8") as sf:
            html_content = sf.read()
    except Exception as e:
        print(f"Warning: Could not read {src_file}. Skipping injection.")
        return match.group(0)
        
    # Create the JS variable name
    var_name = frame_id.replace("-", "_") + "_html"
    
    # We will remove the src attribute and leave the iframe empty
    return f'<iframe id="{frame_id}"{extras}></iframe>\\n<!-- INJECT_{var_name} -->'

content_modified = iframe_pattern.sub(replacer, content)

# Now generate the script block to inject srcdoc
injection_scripts = []
for match in iframe_pattern.finditer(content):
    frame_id = match.group(1)
    src_file = match.group(2)
    var_name = frame_id.replace("-", "_") + "_html"
    
    try:
        with open(src_file, "r", encoding="utf-8") as sf:
            html_content = sf.read()
            # Escape backslashes, backticks, dollar signs, and closing script tags
            escaped_html = html_content.replace("\\\\", "\\\\\\\\").replace("`", "\\\\`").replace("$", "\\\\$").replace("</script>", "<\\\\/script>")
            injection_scripts.append(f"const {var_name} = `{escaped_html}`;")
            injection_scripts.append(f"document.getElementById('{frame_id}').srcdoc = {var_name};")
    except:
        pass

if injection_scripts:
    script_block = "<script>\\n" + "\\n".join(injection_scripts) + "\\n</script>\\n</body>"
    content_modified = content_modified.replace("</body>", script_block)

with open("../index.html", "w", encoding="utf-8") as f:
    f.write(content_modified)

print("Successfully generated self-contained ../index.html!")
'''

with open("combine_presentation.py", "w", encoding="utf-8") as f:
    f.write(combine_script)
    
print("Created combine_presentation.py successfully!")
