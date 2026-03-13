import json

# Read the file
with open('/Users/lzw/Documents/LobsterAI/lzw/x-reader/twitter_ai_result.json.error', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace Chinese quotes with escaped regular quotes
content = content.replace('"', '\\\"').replace('"', '\\\"')

# Write back
with open('/Users/lzw/Documents/LobsterAI/lzw/x-reader/twitter_ai_result.json', 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
try:
    with open('/Users/lzw/Documents/LobsterAI/lzw/x-reader/twitter_ai_result.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    count = len(data["results"])
    print(f"Success! Valid JSON with {count} results")
except Exception as e:
    print(f"Error: {e}")
