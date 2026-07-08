import os
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
    return f'<iframe id="{frame_id}"{extras}></iframe>\n<!-- INJECT_{var_name} -->'

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
            escaped_html = html_content.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$").replace("</script>", "<\\/script>")
            injection_scripts.append(f"const {var_name} = `{escaped_html}`;")
            injection_scripts.append(f"document.getElementById('{frame_id}').srcdoc = {var_name};")
    except:
        pass

if injection_scripts:
    script_block = "<script>\n" + "\n".join(injection_scripts) + "\n</script>\n</body>"
    content_modified = content_modified.replace("</body>", script_block)

with open("../index.html", "w", encoding="utf-8") as f:
    f.write(content_modified)

print("Successfully generated self-contained ../index.html!")
