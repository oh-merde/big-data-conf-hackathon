# Repo Guard

**Repo Guard** is an automated security scanning system that analyzes GitHub repositories to detect vulnerable packages and their versions. The system fetches vulnerability data from [OSV.dev](https://osv.dev) and intelligently scans your repository's dependency files to identify potential security risks.

## Overview

Repo Guard provides a comprehensive solution for vulnerability detection by:

1. **Fetching vulnerability data** from OSV.dev's vulnerability database
2. **Cloning and analyzing repositories** to extract package dependencies
3. **Detecting package ecosystems** (npm, PyPI, RubyGems, Maven, etc.) automatically
4. **Matching packages and versions** against known vulnerabilities
5. **Reporting security findings** with detailed vulnerability information

## How It Works

### 1. Vulnerability Data Collection

The system downloads the complete vulnerability database from OSV.dev, which includes security advisories from multiple sources including GitHub Security Advisories, PyPI, npm, and more. The data is filtered and stored in CSV format for efficient querying.

**Key Features:**
- Fetches vulnerabilities for multiple ecosystems (npm, PyPI, and more)
- Stores vulnerability details including CVE IDs, severity scores, affected versions, and descriptions
- Maintains an up-to-date local database for fast lookups

### 2. Repository Analysis

When you provide a repository URL, Repo Guard:

- **Clones the repository** to a temporary directory
- **Scans for dependency files** such as:
  - `requirements.txt`, `Pipfile`, `pyproject.toml` (Python/PyPI)
  - `package.json`, `package-lock.json`, `yarn.lock` (JavaScript/npm)
  - `Gemfile`, `Gemfile.lock` (Ruby/RubyGems)
  - And many more ecosystem-specific files
- **Extracts package names and versions** from these files
- **Classifies the ecosystem** automatically based on detected dependency files

### 3. Vulnerability Matching

The system performs intelligent matching by:

- **Ecosystem classification**: Automatically identifies whether your repository uses npm, PyPI, or other package managers
- **Package version checking**: Compares each package version against the vulnerability database
- **Version range analysis**: Determines if installed versions fall within vulnerable ranges
- **Vulnerability identification**: Returns specific vulnerability IDs (e.g., `GHSA-m42m-m8cr-8m58`, `PYSEC-2018-33`) when matches are found

### 4. Reporting

Results are provided in a structured format showing:
- **Package name and version** from your repository
- **Match status** (TRUE/FALSE) indicating if a vulnerability was found
- **Vulnerability ID** for detailed lookup and remediation
- **Ecosystem** classification for context

## Components

### Core Scripts

- **`utils/fetch_vulnerabilities_to_csv.py`**: Downloads and processes vulnerability data from OSV.dev
- **`clone_repo.py`**: Handles repository cloning and file extraction
- **`scripts/environment_mapper.py`**: Detects package ecosystems from repository files
- **`scripts/build_vector_store.py`**: Creates vector embeddings for efficient vulnerability searching

### Data Files

- **`data/vulnerabilities_npm_pypi.csv`**: Complete vulnerability database for npm and PyPI
- **`data/vulnerabilities_npm_pypi_lean.csv`**: Filtered subset for faster processing
- **`data/ground_truth.csv`**: Test cases and validation data

## Supported Ecosystems

Repo Guard currently supports detection and scanning for:

- **Python**: PyPI (requirements.txt, Pipfile, pyproject.toml, setup.py)
- **JavaScript**: npm (package.json, package-lock.json, yarn.lock, pnpm-lock.yaml)

## Usage Example

```python
# The system analyzes a repository and produces results like:

ecosystem,repo,filename,package,version,match,vulnerabilityid
pypi,https://github.com/ai-yann/vilnius-workshop,requirements.txt,cohere,5.0.0,FALSE,
pypi,https://github.com/ai-yann/vilnius-workshop,requirements.txt,numpy,1.24.0,TRUE,PYSEC-2018-33
pypi,https://github.com/ai-yann/vilnius-workshop,requirements.txt,jupyter,1.0.0,TRUE,PYSEC-2020-215
```

In this example:
- `cohere 5.0.0` has no known vulnerabilities (FALSE)
- `numpy 1.24.0` matches vulnerability `PYSEC-2018-33` (TRUE)
- `jupyter 1.0.0` matches vulnerability `PYSEC-2020-215` (TRUE)

## Benefits

- **Automated Detection**: No manual checking required - just provide a repository URL
- **Multi-Ecosystem Support**: Works across multiple programming languages and package managers
- **Comprehensive Database**: Leverages OSV.dev's extensive vulnerability database
- **Fast Analysis**: Efficient vector-based searching for quick results
- **Detailed Reporting**: Provides specific vulnerability IDs for remediation

## Data Sources

Repo Guard uses the [OSV (Open Source Vulnerabilities) database](https://osv.dev), which aggregates vulnerability information from:
- GitHub Security Advisories
- npm Security Advisories
- PyPI Security Advisories
- National Vulnerability Database (NVD)
- And many other sources

This ensures comprehensive coverage of known security vulnerabilities across multiple ecosystems.

