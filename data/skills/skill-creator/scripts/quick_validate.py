#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version
"""

import sys
import os
import re
import yaml
from pathlib import Path

def validate_skill(skill_path):
    """Basic validation of a skill"""
    skill_path = Path(skill_path)

    # Check SKILL.md exists
    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return False, "SKILL.md not found"

    # Read and validate frontmatter
    content = skill_md.read_text(encoding="utf-8-sig")
    if not content.startswith('---'):
        return False, "No YAML frontmatter found"

    # Extract frontmatter
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter_text = match.group(1)

    # Parse YAML frontmatter
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter must be a YAML dictionary"
    except yaml.YAMLError as e:
        return False, f"Invalid YAML in frontmatter: {e}"

    # Define allowed properties
    ALLOWED_PROPERTIES = {
        'name', 'description', 'keywords', 'tools', 'license',
        'allowed-tools', 'metadata'
    }

    # Check for unexpected properties (excluding nested keys under metadata)
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected_keys:
        return False, (
            f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected_keys))}. "
            f"Allowed properties are: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )

    # Check required fields
    if 'name' not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if 'description' not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    # Extract name for validation
    name = frontmatter.get('name', '')
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if name:
        # Check naming convention (hyphen-case: lowercase with hyphens)
        if not re.match(r'^[a-z0-9-]+$', name):
            return False, f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)"
        if name.startswith('-') or name.endswith('-') or '--' in name:
            return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
        # Check name length (max 64 characters per spec)
        if len(name) > 64:
            return False, f"Name is too long ({len(name)} characters). Maximum is 64 characters."

    # Extract and validate description
    description = frontmatter.get('description', '')
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if not description:
        return False, "Description cannot be empty"
    if 'TODO' in description.upper():
        return False, "Description still contains a TODO placeholder"
    if description:
        # Check for angle brackets
        if '<' in description or '>' in description:
            return False, "Description cannot contain angle brackets (< or >)"
        # Check description length (max 1024 characters per spec)
        if len(description) > 1024:
            return False, f"Description is too long ({len(description)} characters). Maximum is 1024 characters."

    for field in ('keywords', 'tools'):
        if field not in frontmatter:
            continue
        value = frontmatter.get(field)
        if not isinstance(value, str):
            return False, f"{field.capitalize()} must be a comma-separated string, got {type(value).__name__}"
        value = value.strip()
        if not value:
            return False, f"{field.capitalize()} must be omitted instead of left empty"
        if 'TODO' in value.upper():
            return False, f"{field.capitalize()} still contains a TODO placeholder"

    if name != skill_path.name:
        return False, f"Skill name '{name}' must match directory name '{skill_path.name}'"

    known_tools = {
        'request_user_input', 'list_files', 'read_file', 'search_files',
        'glob_files', 'web_fetch', 'use_skill', 'read_skill_resource',
        'save_memory', 'write_file', 'delete_file', 'task', 'run_command',
        'propose_edit', 'create_ppt_master_deck',
    }
    declared_tools = {
        item.strip() for item in str(frontmatter.get('tools') or '').split(',')
        if item.strip()
    }
    unknown_tools = declared_tools - known_tools
    if unknown_tools:
        return False, f"Unknown Code tool(s): {', '.join(sorted(unknown_tools))}"

    if len(content.splitlines()) >= 500:
        return False, "SKILL.md must stay below 500 lines; move details into packaged resources"

    body_without_fences = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', body_without_fences):
        if '://' in target or target.startswith('#'):
            continue
        relative = target.split('#', 1)[0]
        referenced = (skill_path / relative).resolve()
        try:
            referenced.relative_to(skill_path.resolve())
        except ValueError:
            return False, f"Resource link escapes skill directory: {target}"
        if not referenced.is_file():
            return False, f"Referenced resource does not exist: {target}"

    if '[TODO' in content.upper():
        return False, "SKILL.md body still contains TODO placeholders"

    # The initializer creates illustrative resource files. They must not leak
    # into a finished package unchanged: implement them or delete them.
    scaffold_markers = {
        'scripts/example.py': (
            'This is a placeholder script',
            '# TODO: Add actual script logic here',
        ),
        'references/api_reference.md': (
            'This is a placeholder for detailed reference documentation.',
        ),
        'assets/example_asset.txt': (
            'This placeholder represents where asset files would be stored.',
        ),
    }
    for relative_path, markers in scaffold_markers.items():
        resource_path = skill_path / relative_path
        if not resource_path.is_file():
            continue
        try:
            resource_content = resource_path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:
            continue
        if any(marker in resource_content for marker in markers):
            return False, (
                f"Scaffold resource '{relative_path}' is still unchanged. "
                "Implement it or delete it before packaging."
            )

    return True, "Skill is valid!"

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        sys.exit(1)
    
    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
