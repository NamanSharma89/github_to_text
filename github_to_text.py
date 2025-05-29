#!/usr/bin/env python3
"""
GitHub Repository to Text Converter - Space Optimized for LLM Ingestion

This script converts a GitHub repository to a single text file format,
optimized for minimal token usage while maintaining LLM readability.

Usage:
    python github_to_text.py --repo https://github.com/username/repo.git --output output.txt [options]
    python github_to_text.py --local /path/to/local/repo --output output.txt [options]
    python github_to_text.py --repo https://github.com/user/repo.git --output optimized.txt --format compact

Features:
- Processes all text-based files in a repository with space optimization
- Preserves file structure and important context
- Filters binary files, large files, and unwanted files (like .git)
- Option to include/exclude specific file types or directories
- Smart context preservation with file metadata
- Space optimization: removes unnecessary whitespace, compacts formatting
"""

import os
import sys
import argparse
import subprocess
import tempfile
import shutil
import re
import mimetypes
import fnmatch
import json
from pathlib import Path
from typing import List, Set, Dict, Tuple, Optional

# Initialize mimetypes
mimetypes.init()


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Convert a GitHub repository to a single text file for LLM ingestion (space optimized)"
    )
    
    # Source options - either GitHub URL or local path
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--repo", 
        type=str, 
        help="GitHub repository URL (https://github.com/username/repo.git)"
    )
    source_group.add_argument(
        "--local", 
        type=str, 
        help="Local path to repository"
    )
    
    # Output file
    parser.add_argument(
        "--output", 
        type=str, 
        required=True, 
        help="Output text file path"
    )
    
    # Space optimization options
    parser.add_argument(
        "--optimize-level", 
        type=int, 
        choices=[1, 2, 3],
        default=2,
        help="Optimization level: 1=minimal, 2=moderate, 3=aggressive (default: 2)"
    )
    
    parser.add_argument(
        "--preserve-comments", 
        action="store_true",
        help="Preserve comments (increases size but helps LLM understanding)"
    )
    
    parser.add_argument(
        "--preserve-docstrings", 
        action="store_true",
        default=True,
        help="Preserve docstrings and function documentation"
    )
    
    # Filtering options
    parser.add_argument(
        "--exclude-dirs", 
        type=str, 
        nargs="+", 
        default=[".git", "node_modules", "__pycache__", "venv", ".env", ".venv", "dist", "build"],
        help="Directories to exclude"
    )
    
    parser.add_argument(
        "--ignore-file", 
        type=str,
        help="Path to a file containing patterns of directories to ignore"
    )
    
    parser.add_argument(
        "--ignore-patterns", 
        type=str, 
        nargs="+", 
        default=[],
        help="Glob patterns for directories to ignore"
    )
    
    parser.add_argument(
        "--verbose-ignore", 
        action="store_true",
        help="Print verbose information about ignored directories"
    )
    
    parser.add_argument(
        "--exclude-files", 
        type=str, 
        nargs="+", 
        default=[".DS_Store", ".gitignore", "package-lock.json", "yarn.lock"],
        help="Files to exclude"
    )
    
    parser.add_argument(
        "--max-file-size", 
        type=int, 
        default=1000000,  # 1MB
        help="Maximum file size in bytes (default: 1000000)"
    )
    
    parser.add_argument(
        "--include-extensions", 
        type=str, 
        nargs="+", 
        help="Only include files with these extensions"
    )
    
    parser.add_argument(
        "--exclude-extensions", 
        type=str, 
        nargs="+", 
        default=[".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".zip", ".gz", ".tar", ".mp3", ".mp4", ".avi", ".mov", ".exe", ".bin", ".dat", ".db", ".sqlite", ".pyc"],
        help="Exclude files with these extensions"
    )
    
    parser.add_argument(
        "--format", 
        type=str, 
        choices=["simple", "markdown", "jsonl", "compact"],
        default="compact",
        help="Output format (compact: optimized for LLM with minimal tokens)"
    )
    
    parser.add_argument(
        "--include-repo-info", 
        action="store_true",
        help="Include repository information at the top of the output"
    )
    
    parser.add_argument(
        "--chunk-size", 
        type=int, 
        default=0,
        help="Split output into chunks of this many bytes (0 means no chunking)"
    )
    
    parser.add_argument(
        "--create-example-ignore", 
        type=str,
        help="Create an example ignore file at the specified path"
    )
    
    return parser.parse_args()


def optimize_code_content(content: str, file_ext: str, optimize_level: int, preserve_comments: bool, preserve_docstrings: bool) -> str:
    """Optimize code content by removing unnecessary whitespace and formatting"""
    
    # Level 1: Basic optimization
    if optimize_level >= 1:
        # Remove trailing whitespace
        content = re.sub(r'[ \t]+$', '', content, flags=re.MULTILINE)
        
        # Replace multiple consecutive empty lines with single empty line
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
        
        # Remove leading/trailing empty lines
        content = content.strip()
    
    # Level 2: Moderate optimization
    if optimize_level >= 2:
        # Language-specific optimizations
        if file_ext in ['.py']:
            content = optimize_python_code(content, preserve_comments, preserve_docstrings)
        elif file_ext in ['.js', '.jsx', '.ts', '.tsx']:
            content = optimize_javascript_code(content, preserve_comments, preserve_docstrings)
        elif file_ext in ['.java', '.c', '.cpp', '.h', '.hpp']:
            content = optimize_c_like_code(content, preserve_comments, preserve_docstrings)
        elif file_ext in ['.html', '.xml']:
            content = optimize_markup_code(content)
        elif file_ext in ['.css', '.scss', '.sass']:
            content = optimize_css_code(content, preserve_comments)
        elif file_ext in ['.json']:
            content = optimize_json_code(content)
        else:
            # Generic optimization for other text files
            content = optimize_generic_code(content, preserve_comments)
    
    # Level 3: Aggressive optimization
    if optimize_level >= 3:
        # More aggressive space removal while preserving syntax
        content = aggressive_space_optimization(content, file_ext)
    
    return content


def optimize_python_code(content: str, preserve_comments: bool, preserve_docstrings: bool) -> str:
    """Optimize Python code specifically"""
    lines = content.split('\n')
    optimized_lines = []
    in_multiline_string = False
    string_delimiter = None
    
    for line in lines:
        original_line = line
        stripped = line.strip()
        
        # Handle multiline strings/docstrings
        if '"""' in line or "'''" in line:
            if not in_multiline_string:
                in_multiline_string = True
                string_delimiter = '"""' if '"""' in line else "'''"
                if preserve_docstrings:
                    optimized_lines.append(line)
                continue
            elif string_delimiter in line:
                in_multiline_string = False
                if preserve_docstrings:
                    optimized_lines.append(line)
                continue
        
        if in_multiline_string:
            if preserve_docstrings:
                optimized_lines.append(line)
            continue
        
        # Skip empty lines and comments based on settings
        if not stripped:
            continue
        if stripped.startswith('#') and not preserve_comments:
            continue
        
        # Optimize spacing around operators and keywords
        line = re.sub(r'\s*=\s*', '=', line)
        line = re.sub(r'\s*\+\s*', '+', line)
        line = re.sub(r'\s*-\s*', '-', line)
        line = re.sub(r'\s*\*\s*', '*', line)
        line = re.sub(r'\s*/\s*', '/', line)
        line = re.sub(r'\s*<\s*', '<', line)
        line = re.sub(r'\s*>\s*', '>', line)
        line = re.sub(r'\s*==\s*', '==', line)
        line = re.sub(r'\s*!=\s*', '!=', line)
        line = re.sub(r'\s*<=\s*', '<=', line)
        line = re.sub(r'\s*>=\s*', '>=', line)
        
        # Preserve minimal indentation for Python syntax
        indent_match = re.match(r'^(\s*)', original_line)
        if indent_match:
            indent = indent_match.group(1)
            # Convert tabs to single space, preserve relative indentation
            indent = re.sub(r'\t', ' ', indent)
            # Reduce multiple spaces to minimum needed
            indent_level = len(indent.replace('    ', ' '))
            line = ' ' * indent_level + line.strip()
        
        optimized_lines.append(line)
    
    return '\n'.join(optimized_lines)


def optimize_javascript_code(content: str, preserve_comments: bool, preserve_docstrings: bool) -> str:
    """Optimize JavaScript/TypeScript code"""
    # Remove single-line comments if not preserving
    if not preserve_comments:
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
    
    # Remove multi-line comments if not preserving docstrings
    if not preserve_docstrings:
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # Optimize spacing around common operators
    content = re.sub(r'\s*([=+\-*/<>!]=?)\s*', r'\1', content)
    content = re.sub(r'\s*([{}();,])\s*', r'\1', content)
    
    # Remove extra spaces but preserve line breaks for readability
    lines = content.split('\n')
    optimized_lines = []
    
    for line in lines:
        line = line.strip()
        if line:
            # Preserve minimal spacing for readability
            line = re.sub(r'\s+', ' ', line)
            optimized_lines.append(line)
    
    return '\n'.join(optimized_lines)


def optimize_c_like_code(content: str, preserve_comments: bool, preserve_docstrings: bool) -> str:
    """Optimize C/C++/Java code"""
    # Remove comments if not preserving
    if not preserve_comments:
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
    if not preserve_docstrings:
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # Optimize spacing
    content = re.sub(r'\s*([=+\-*/<>!]=?)\s*', r'\1', content)
    content = re.sub(r'\s*([{}();,])\s*', r'\1', content)
    
    lines = content.split('\n')
    optimized_lines = []
    
    for line in lines:
        line = line.strip()
        if line:
            line = re.sub(r'\s+', ' ', line)
            optimized_lines.append(line)
    
    return '\n'.join(optimized_lines)


def optimize_markup_code(content: str) -> str:
    """Optimize HTML/XML code"""
    # Remove extra whitespace between tags
    content = re.sub(r'>\s+<', '><', content)
    
    # Remove leading/trailing whitespace from lines
    lines = content.split('\n')
    optimized_lines = []
    
    for line in lines:
        line = line.strip()
        if line:
            optimized_lines.append(line)
    
    return '\n'.join(optimized_lines)


def optimize_css_code(content: str, preserve_comments: bool) -> str:
    """Optimize CSS code"""
    # Remove comments if not preserving
    if not preserve_comments:
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # Remove extra spaces around CSS syntax
    content = re.sub(r'\s*([{}:;,])\s*', r'\1', content)
    content = re.sub(r';\s*}', '}', content)
    
    lines = content.split('\n')
    optimized_lines = []
    
    for line in lines:
        line = line.strip()
        if line:
            optimized_lines.append(line)
    
    return '\n'.join(optimized_lines)


def optimize_json_code(content: str) -> str:
    """Optimize JSON by minifying it"""
    try:
        # Parse and re-serialize JSON to remove all unnecessary whitespace
        parsed = json.loads(content)
        return json.dumps(parsed, separators=(',', ':'))
    except json.JSONDecodeError:
        # If not valid JSON, just remove extra whitespace
        return optimize_generic_code(content, False)


def optimize_generic_code(content: str, preserve_comments: bool) -> str:
    """Generic optimization for other file types"""
    lines = content.split('\n')
    optimized_lines = []
    
    for line in lines:
        line = line.strip()
        if line:
            # Remove common comment patterns if not preserving
            if not preserve_comments:
                if line.startswith('#') or line.startswith('//') or line.startswith('--'):
                    continue
            optimized_lines.append(line)
    
    return '\n'.join(optimized_lines)


def aggressive_space_optimization(content: str, file_ext: str) -> str:
    """Aggressive space optimization while preserving syntax"""
    # Only apply to languages where it's safe
    if file_ext in ['.json', '.css', '.scss']:
        # Remove all unnecessary whitespace
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'\s*([{}();,:])\s*', r'\1', content)
    
    return content


def clone_repository(repo_url: str) -> str:
    """Clone a GitHub repository to a temporary directory and return the path"""
    print(f"Cloning repository {repo_url}...")
    temp_dir = tempfile.mkdtemp()
    
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, temp_dir], 
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return temp_dir
    except subprocess.CalledProcessError as e:
        print(f"Error cloning repository: {e.stderr.decode()}")
        shutil.rmtree(temp_dir)
        sys.exit(1)


def get_repo_info(repo_path: str) -> Dict[str, str]:
    """Get information about the repository"""
    try:
        origin_url = subprocess.run(
            ["git", "-C", repo_path, "config", "--get", "remote.origin.url"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        ).stdout.decode().strip()
    except subprocess.CalledProcessError:
        origin_url = "Unknown"
    
    try:
        last_commit = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--pretty=format:%h - %an, %ar : %s"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        ).stdout.decode().strip()
    except subprocess.CalledProcessError:
        last_commit = "Unknown"
    
    try:
        branch = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        ).stdout.decode().strip()
    except subprocess.CalledProcessError:
        branch = "Unknown"
    
    return {
        "url": origin_url,
        "branch": branch,
        "last_commit": last_commit
    }


def is_binary_file(file_path: str) -> bool:
    """Check if a file is binary using a simple heuristic approach"""
    mime_type, _ = mimetypes.guess_type(file_path)
    
    if mime_type and mime_type.startswith(('text/', 'application/json', 'application/xml', 'application/javascript')):
        return False
    
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(8192)
            
        try:
            chunk.decode('utf-8')
            return False
        except UnicodeDecodeError:
            return True
            
    except Exception:
        return True


def create_example_ignore_file(path: str) -> None:
    """Create an example ignore file with common patterns"""
    example_content = """# Example ignore file for github_to_text.py
# Add patterns to ignore directories or files, one per line
# Use glob-style patterns (* matches any characters, ** for recursive matching)

# Common patterns to ignore
**/temp/**
**/logs/**
**/backup/**
**/cache/**
**/.vscode/**
**/.idea/**
**/test/fixtures/**
**/test/data/**
**/docs/examples/**
**/tools/scripts/**

# Example of ignoring specific files by pattern
**/settings.dev.json
**/*-backup.*
**/*.min.js
**/*.min.css
**/*.log
"""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(example_content)
        print(f"Created example ignore file at {path}")
    except Exception as e:
        print(f"Error creating example ignore file: {e}")
        sys.exit(1)


def load_ignore_patterns(ignore_file_path: str) -> List[str]:
    """Load ignore patterns from a file (one pattern per line)"""
    patterns = []
    try:
        with open(ignore_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    patterns.append(line)
        return patterns
    except Exception as e:
        print(f"Warning: Could not load ignore file {ignore_file_path}: {e}")
        return []


def path_matches_pattern(path: str, patterns: List[str]) -> bool:
    """Check if a path matches any of the provided glob patterns"""
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


def should_include_file(file_path: str, args, ignore_patterns: List[str]) -> bool:
    """Determine if a file should be included based on filtering criteria"""
    path = Path(file_path)
    rel_path_str = str(path)
    
    if path_matches_pattern(rel_path_str, ignore_patterns):
        if args.verbose_ignore:
            print(f"Ignoring file (matched pattern): {rel_path_str}")
        return False
    
    for excluded_dir in args.exclude_dirs:
        if excluded_dir in path.parts:
            if args.verbose_ignore:
                print(f"Ignoring file (excluded dir): {rel_path_str}")
            return False
    
    if path.name in args.exclude_files:
        if args.verbose_ignore:
            print(f"Ignoring file (excluded file): {rel_path_str}")
        return False
    
    if path.stat().st_size > args.max_file_size:
        if args.verbose_ignore:
            print(f"Ignoring file (size > {args.max_file_size}): {rel_path_str}")
        return False
    
    ext = path.suffix.lower()
    if args.include_extensions and ext not in args.include_extensions:
        if args.verbose_ignore:
            print(f"Ignoring file (not in included extensions): {rel_path_str}")
        return False
    if ext in args.exclude_extensions:
        if args.verbose_ignore:
            print(f"Ignoring file (in excluded extensions): {rel_path_str}")
        return False
    
    if is_binary_file(file_path):
        if args.verbose_ignore:
            print(f"Ignoring file (binary): {rel_path_str}")
        return False
    
    return True


def walk_repository(repo_path: str, args, ignore_patterns: List[str]) -> List[str]:
    """Walk through repository and collect files to process"""
    files_to_process = []
    ignored_dirs_count = 0
    ignored_files_count = 0
    
    for root, dirs, files in os.walk(repo_path):
        rel_root = os.path.relpath(root, repo_path)
        
        dirs_to_remove = []
        for d in dirs:
            dir_path = os.path.join(rel_root, d)
            
            if d in args.exclude_dirs:
                dirs_to_remove.append(d)
                ignored_dirs_count += 1
                if args.verbose_ignore:
                    print(f"Ignoring directory (in exclude list): {dir_path}")
                continue
                
            if path_matches_pattern(dir_path, ignore_patterns):
                dirs_to_remove.append(d)
                ignored_dirs_count += 1
                if args.verbose_ignore:
                    print(f"Ignoring directory (matched pattern): {dir_path}")
                continue
                
        for d in dirs_to_remove:
            dirs.remove(d)
        
        for file in files:
            file_path = os.path.join(root, file)
            if should_include_file(file_path, args, ignore_patterns):
                files_to_process.append(file_path)
            else:
                ignored_files_count += 1
    
    if args.verbose_ignore:
        print(f"Ignored {ignored_dirs_count} directories and {ignored_files_count} files")
    
    return files_to_process


def get_file_language(file_path: str) -> str:
    """Determine the programming language of a file based on extension"""
    ext_to_language = {
        '.py': 'python', '.js': 'javascript', '.jsx': 'javascript', '.ts': 'typescript', '.tsx': 'typescript',
        '.html': 'html', '.css': 'css', '.scss': 'scss', '.sass': 'sass', '.java': 'java',
        '.c': 'c', '.cpp': 'cpp', '.h': 'c', '.hpp': 'cpp', '.go': 'go', '.rs': 'rust',
        '.rb': 'ruby', '.php': 'php', '.swift': 'swift', '.kt': 'kotlin', '.sh': 'bash',
        '.md': 'markdown', '.json': 'json', '.xml': 'xml', '.yml': 'yaml', '.yaml': 'yaml',
        '.toml': 'toml', '.sql': 'sql', '.r': 'r', '.dart': 'dart'
    }
    
    ext = Path(file_path).suffix.lower()
    return ext_to_language.get(ext, 'text')


def format_file_content(file_path: str, repo_path: str, args) -> str:
    """Format file content based on the selected format with optimization"""
    relative_path = os.path.relpath(file_path, repo_path)
    language = get_file_language(file_path)
    file_ext = Path(file_path).suffix.lower()
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {relative_path}: {e}")
        content = f"[Error reading file: {e}]"
    
    # Apply optimization if not in simple mode
    if args.format != "simple":
        content = optimize_code_content(
            content, 
            file_ext, 
            args.optimize_level, 
            args.preserve_comments, 
            args.preserve_docstrings
        )
    
    if args.format == "simple":
        return f"{content}\n\n"
    
    elif args.format == "markdown":
        return f"## File: {relative_path}\n\n```{language}\n{content}\n```\n\n"
    
    elif args.format == "compact":
        # Ultra-compact format for LLM ingestion
        return f"=== {relative_path} ({language}) ===\n{content}\n\n"
    
    elif args.format == "jsonl":
        file_obj = {
            "path": relative_path,
            "language": language,
            "content": content
        }
        return json.dumps(file_obj, separators=(',', ':')) + "\n"


def process_repository(repo_path: str, args, ignore_patterns: List[str]) -> List[str]:
    """Process the repository and generate the output text"""
    files = walk_repository(repo_path, args, ignore_patterns)
    print(f"Found {len(files)} files to process")
    
    output_chunks = []
    current_chunk = ""
    
    if args.include_repo_info:
        repo_info = get_repo_info(repo_path)
        if args.format == "simple":
            repo_header = f"Repository: {repo_info['url']}\nBranch: {repo_info['branch']}\nLast Commit: {repo_info['last_commit']}\n\n"
        elif args.format == "markdown":
            repo_header = f"# Repository Information\n\n- **URL:** {repo_info['url']}\n- **Branch:** {repo_info['branch']}\n- **Last Commit:** {repo_info['last_commit']}\n\n---\n\n"
        elif args.format == "compact":
            repo_header = f"=== REPO INFO ===\nURL: {repo_info['url']}\nBranch: {repo_info['branch']}\nCommit: {repo_info['last_commit']}\n\n"
        elif args.format == "jsonl":
            repo_header = json.dumps({
                "type": "repository_info",
                "url": repo_info['url'],
                "branch": repo_info['branch'],
                "last_commit": repo_info['last_commit']
            }, separators=(',', ':')) + "\n"
        
        current_chunk += repo_header
    
    for idx, file_path in enumerate(files):
        relative_path = os.path.relpath(file_path, repo_path)
        print(f"Processing {idx+1}/{len(files)}: {relative_path}")
        
        file_content = format_file_content(file_path, repo_path, args)
        
        if args.chunk_size > 0:
            if len(current_chunk) + len(file_content) > args.chunk_size:
                output_chunks.append(current_chunk)
                current_chunk = file_content
            else:
                current_chunk += file_content
        else:
            current_chunk += file_content
    
    if current_chunk:
        output_chunks.append(current_chunk)
    
    return output_chunks


def write_output(chunks: List[str], output_path: str, args) -> None:
    """Write the output to file(s)"""
    if args.chunk_size > 0 and len(chunks) > 1:
        base_name, ext = os.path.splitext(output_path)
        for idx, chunk in enumerate(chunks):
            chunk_path = f"{base_name}_{idx+1}{ext}"
            with open(chunk_path, 'w', encoding='utf-8') as f:
                f.write(chunk)
            print(f"Wrote chunk {idx+1}/{len(chunks)} to {chunk_path} ({len(chunk)} bytes)")
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(''.join(chunks))
        total_size = len(''.join(chunks))
        print(f"Wrote output to {output_path} ({total_size} bytes)")


def main():
    args = parse_arguments()
    
    if args.create_example_ignore:
        create_example_ignore_file(args.create_example_ignore)
        print("Example ignore file created. Exiting.")
        sys.exit(0)
    
    ignore_patterns = list(args.ignore_patterns)
    
    if args.ignore_file:
        file_patterns = load_ignore_patterns(args.ignore_file)
        if file_patterns:
            print(f"Loaded {len(file_patterns)} ignore patterns from {args.ignore_file}")
            ignore_patterns.extend(file_patterns)
    
    if args.verbose_ignore:
        print(f"Using {len(ignore_patterns)} ignore patterns: {ignore_patterns}")
        print(f"Excluding directories: {args.exclude_dirs}")
        print(f"Excluding files: {args.exclude_files}")
        print(f"Optimization level: {args.optimize_level}")
        print(f"Preserve comments: {args.preserve_comments}")
        print(f"Preserve docstrings: {args.preserve_docstrings}")
    
    if args.repo:
        repo_path = clone_repository(args.repo)
        cleanup_needed = True
    else:
        repo_path = args.local
        cleanup_needed = False
    
    try:
        output_chunks = process_repository(repo_path, args, ignore_patterns)
        write_output(output_chunks, args.output, args)
        
    finally:
        if cleanup_needed:
            print(f"Cleaning up temporary directory {repo_path}")
            shutil.rmtree(repo_path)


if __name__ == "__main__":
    main()