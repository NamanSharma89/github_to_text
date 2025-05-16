#!/usr/bin/env python3
"""
GitHub Repository to Text Converter

This script converts a GitHub repository to a single text file format,
suitable for ingestion by Large Language Models (LLMs).

Usage:
    python github_to_text.py --repo https://github.com/username/repo.git --output output.txt [options]
    python github_to_text.py --local /path/to/local/repo --output output.txt [options]

Features:
- Processes all text-based files in a repository
- Preserves file structure and important context
- Filters binary files, large files, and unwanted files (like .git)
- Option to include/exclude specific file types or directories
- Smart context preservation with file metadata
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
        description="Convert a GitHub repository to a single text file for LLM ingestion"
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
    
    # Filtering options
    parser.add_argument(
        "--exclude-dirs", 
        type=str, 
        nargs="+", 
        default=[".git", "node_modules", "__pycache__", "venv", ".env", ".venv", "dist", "build"],
        help="Directories to exclude (default: .git node_modules __pycache__ venv .env .venv dist build)"
    )
    
    parser.add_argument(
        "--ignore-file", 
        type=str,
        help="Path to a file containing patterns of directories to ignore (one pattern per line)"
    )
    
    parser.add_argument(
        "--ignore-patterns", 
        type=str, 
        nargs="+", 
        default=[],
        help="Glob patterns for directories to ignore (e.g., '**/temp*' '**/logs*')"
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
        help="Files to exclude (default: .DS_Store .gitignore package-lock.json yarn.lock)"
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
        help="Only include files with these extensions (e.g., .py .js .html)"
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
        choices=["simple", "markdown", "jsonl"],
        default="markdown",
        help="Output format (simple: just files concatenated, markdown: with headers, jsonl: one JSON object per line)"
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
    
    # Add the create-example-ignore option
    parser.add_argument(
        "--create-example-ignore", 
        type=str,
        help="Create an example ignore file at the specified path"
    )
    
    return parser.parse_args()


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
    # First use mimetypes to guess based on extension
    mime_type, _ = mimetypes.guess_type(file_path)
    
    # If mimetypes identifies it as text, we're good
    if mime_type and mime_type.startswith(('text/', 'application/json', 'application/xml', 'application/javascript')):
        return False
    
    # For uncertain types or types that look binary, do a content check
    try:
        with open(file_path, 'rb') as f:
            # Read the first 8192 bytes
            chunk = f.read(8192)
            
        # Try to decode as text - if it fails, likely binary
        try:
            chunk.decode('utf-8')
            return False
        except UnicodeDecodeError:
            return True
            
    except Exception:
        # If we can't read the file, assume it's binary to be safe
        return True


# ===== Ignore Pattern Functions =====

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
                # Skip empty lines and comments
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
    
    # Check if file path matches any ignore pattern
    if path_matches_pattern(rel_path_str, ignore_patterns):
        if args.verbose_ignore:
            print(f"Ignoring file (matched pattern): {rel_path_str}")
        return False
    
    # Check if file is in excluded directory
    for excluded_dir in args.exclude_dirs:
        if excluded_dir in path.parts:
            if args.verbose_ignore:
                print(f"Ignoring file (excluded dir): {rel_path_str}")
            return False
    
    # Check if file is in excluded files
    if path.name in args.exclude_files:
        if args.verbose_ignore:
            print(f"Ignoring file (excluded file): {rel_path_str}")
        return False
    
    # Check file size
    if path.stat().st_size > args.max_file_size:
        if args.verbose_ignore:
            print(f"Ignoring file (size > {args.max_file_size}): {rel_path_str}")
        return False
    
    # Check file extension
    ext = path.suffix.lower()
    if args.include_extensions and ext not in args.include_extensions:
        if args.verbose_ignore:
            print(f"Ignoring file (not in included extensions): {rel_path_str}")
        return False
    if ext in args.exclude_extensions:
        if args.verbose_ignore:
            print(f"Ignoring file (in excluded extensions): {rel_path_str}")
        return False
    
    # Check if it's a binary file
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
        
        # Filter out directories based on patterns
        dirs_to_remove = []
        for d in dirs:
            dir_path = os.path.join(rel_root, d)
            
            # Skip excluded directories by name
            if d in args.exclude_dirs:
                dirs_to_remove.append(d)
                ignored_dirs_count += 1
                if args.verbose_ignore:
                    print(f"Ignoring directory (in exclude list): {dir_path}")
                continue
                
            # Skip directories matching patterns
            if path_matches_pattern(dir_path, ignore_patterns):
                dirs_to_remove.append(d)
                ignored_dirs_count += 1
                if args.verbose_ignore:
                    print(f"Ignoring directory (matched pattern): {dir_path}")
                continue
                
        # Remove filtered directories
        for d in dirs_to_remove:
            dirs.remove(d)
        
        # Process files
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
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.html': 'html',
        '.css': 'css',
        '.scss': 'scss',
        '.sass': 'sass',
        '.java': 'java',
        '.c': 'c',
        '.cpp': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.sh': 'bash',
        '.md': 'markdown',
        '.json': 'json',
        '.xml': 'xml',
        '.yml': 'yaml',
        '.yaml': 'yaml',
        '.toml': 'toml',
        '.sql': 'sql',
        '.r': 'r',
        '.dart': 'dart'
    }
    
    ext = Path(file_path).suffix.lower()
    return ext_to_language.get(ext, 'text')


def format_file_content(file_path: str, repo_path: str, args) -> str:
    """Format file content based on the selected format"""
    relative_path = os.path.relpath(file_path, repo_path)
    language = get_file_language(file_path)
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {relative_path}: {e}")
        content = f"[Error reading file: {e}]"
    
    if args.format == "simple":
        return f"{content}\n\n"
    
    elif args.format == "markdown":
        return f"## File: {relative_path}\n\n```{language}\n{content}\n```\n\n"
    
    elif args.format == "jsonl":
        import json
        file_obj = {
            "path": relative_path,
            "language": language,
            "content": content
        }
        return json.dumps(file_obj) + "\n"


def process_repository(repo_path: str, args, ignore_patterns: List[str]) -> List[str]:
    """Process the repository and generate the output text"""
    files = walk_repository(repo_path, args, ignore_patterns)
    print(f"Found {len(files)} files to process")
    
    output_chunks = []
    current_chunk = ""
    
    # Add repository information if requested
    if args.include_repo_info:
        repo_info = get_repo_info(repo_path)
        if args.format == "simple":
            repo_header = (
                f"Repository: {repo_info['url']}\n"
                f"Branch: {repo_info['branch']}\n"
                f"Last Commit: {repo_info['last_commit']}\n\n"
            )
        elif args.format == "markdown":
            repo_header = (
                f"# Repository Information\n\n"
                f"- **URL:** {repo_info['url']}\n"
                f"- **Branch:** {repo_info['branch']}\n"
                f"- **Last Commit:** {repo_info['last_commit']}\n\n"
                f"---\n\n"
            )
        elif args.format == "jsonl":
            import json
            repo_header = json.dumps({
                "type": "repository_info",
                "url": repo_info['url'],
                "branch": repo_info['branch'],
                "last_commit": repo_info['last_commit']
            }) + "\n"
        
        current_chunk += repo_header
    
    # Process each file
    for idx, file_path in enumerate(files):
        relative_path = os.path.relpath(file_path, repo_path)
        print(f"Processing {idx+1}/{len(files)}: {relative_path}")
        
        file_content = format_file_content(file_path, repo_path, args)
        
        # Handle chunking if enabled
        if args.chunk_size > 0:
            if len(current_chunk) + len(file_content) > args.chunk_size:
                output_chunks.append(current_chunk)
                current_chunk = file_content
            else:
                current_chunk += file_content
        else:
            current_chunk += file_content
    
    # Add the last chunk if it has content
    if current_chunk:
        output_chunks.append(current_chunk)
    
    return output_chunks


def write_output(chunks: List[str], output_path: str, args) -> None:
    """Write the output to file(s)"""
    if args.chunk_size > 0 and len(chunks) > 1:
        # Write multiple chunks
        base_name, ext = os.path.splitext(output_path)
        for idx, chunk in enumerate(chunks):
            chunk_path = f"{base_name}_{idx+1}{ext}"
            with open(chunk_path, 'w', encoding='utf-8') as f:
                f.write(chunk)
            print(f"Wrote chunk {idx+1}/{len(chunks)} to {chunk_path}")
    else:
        # Write a single file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(''.join(chunks))
        print(f"Wrote output to {output_path}")


def main():
    args = parse_arguments()
    
    # Handle the create-example-ignore option first
    if args.create_example_ignore:
        create_example_ignore_file(args.create_example_ignore)
        print("Example ignore file created. Exiting.")
        sys.exit(0)
    
    # Collect all ignore patterns
    ignore_patterns = list(args.ignore_patterns)
    
    # Add patterns from ignore file if specified
    if args.ignore_file:
        file_patterns = load_ignore_patterns(args.ignore_file)
        if file_patterns:
            print(f"Loaded {len(file_patterns)} ignore patterns from {args.ignore_file}")
            ignore_patterns.extend(file_patterns)
    
    if args.verbose_ignore:
        print(f"Using {len(ignore_patterns)} ignore patterns: {ignore_patterns}")
        print(f"Excluding directories: {args.exclude_dirs}")
        print(f"Excluding files: {args.exclude_files}")
    
    # Get repository path - either by cloning or using local path
    if args.repo:
        repo_path = clone_repository(args.repo)
        cleanup_needed = True
    else:
        repo_path = args.local
        cleanup_needed = False
    
    try:
        # Process the repository
        output_chunks = process_repository(repo_path, args, ignore_patterns)
        
        # Write output
        write_output(output_chunks, args.output, args)
        
    finally:
        # Clean up if we created a temporary directory
        if cleanup_needed:
            print(f"Cleaning up temporary directory {repo_path}")
            shutil.rmtree(repo_path)


if __name__ == "__main__":
    main()