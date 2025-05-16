# Dockerized GitHub-to-Text Converter

This Docker container provides a convenient way to convert GitHub repositories to text format for LLM ingestion, without worrying about dependencies or installation.

## Setup

1. Create a directory for your project and place the following files in it:
   - `Dockerfile`
   - `docker-compose.yml`
   - `github_to_text.py` (your Python script)

2. Create an output directory:
   ```bash
   mkdir output
   ```

3. Build the Docker image:
   ```bash
   docker-compose build
   ```

## Usage

### Using docker-compose (recommended)

Process a GitHub repository:
```bash
docker-compose run --rm github-to-text --repo https://github.com/username/repo.git --output /app/output/result.txt
```

Process with specific options:
```bash
docker-compose run --rm github-to-text --repo https://github.com/username/repo.git --output /app/output/result.md --format markdown --include-repo-info
```

Show help:
```bash
docker-compose run --rm github-to-text --help
```

### Using Docker directly

Process a GitHub repository:
```bash
docker run --rm -v "$(pwd)/output:/app/output" github-to-text --repo https://github.com/username/repo.git --output /app/output/result.txt
```

### Processing local repositories

To process a local repository, you need to mount it into the container:

1. Edit the `docker-compose.yml` file to uncomment and update the local repos volume:
   ```yaml
   volumes:
     - ./output:/app/output
     - /path/to/your/repos:/repos
   ```

2. Run with the `--local` option pointing to the mounted path:
   ```bash
   docker-compose run --rm github-to-text --local /repos/your-repo --output /app/output/result.txt
   ```

## Output Formats

The script supports three output formats:

1. **Simple** (default): Just concatenates files
   ```bash
   docker-compose run --rm github-to-text --repo https://github.com/username/repo.git --output /app/output/result.txt --format simple
   ```

2. **Markdown**: Adds headers and code blocks with proper language tags
   ```bash
   docker-compose run --rm github-to-text --repo https://github.com/username/repo.git --output /app/output/result.md --format markdown
   ```

3. **JSONL**: One JSON object per line for structured processing
   ```bash
   docker-compose run --rm github-to-text --repo https://github.com/username/repo.git --output /app/output/result.jsonl --format jsonl
   ```

## Advanced Options

The script supports various filtering and customization options:

- `--exclude-dirs`: Directories to exclude
- `--exclude-files`: Files to exclude
- `--max-file-size`: Maximum file size in bytes
- `--include-extensions`: Only include files with these extensions
- `--exclude-extensions`: Exclude files with these extensions
- `--include-repo-info`: Include repository information
- `--chunk-size`: Split output into chunks of specified size

For example:
```bash
docker-compose run --rm github-to-text --repo https://github.com/username/repo.git --output /app/output/result.txt --exclude-dirs tests docs --include-extensions .py .js
```

## Notes

- All output files will be saved to the `./output` directory on your host machine
- For large repositories, the process may take some time
- The container automatically cleans up temporary files