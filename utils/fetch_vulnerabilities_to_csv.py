import json
import zipfile
import requests
import tempfile
import os
import io
import pandas as pd
from pathlib import Path

BASE_URL = "https://storage.googleapis.com/osv-vulnerabilities/all.zip"

def create_session():
    """Create configured HTTP session with connection pooling and retries."""
    session = requests.Session()
    session.timeout = 120
    adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50, max_retries=3)
    session.mount('https://', adapter)
    return session

def fetch_data_from_osv(output_dir):
    """Download and extract OSV vulnerabilities zip file."""
    print("Downloading OSV vulnerabilities database...")
    session = create_session()
    response = session.get(BASE_URL, stream=True)
    response.raise_for_status()
    
    print("Extracting zip file...")
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
        zip_ref.extractall(output_dir)
    
    print(f"Extracted to {output_dir}")
    return output_dir

def filter_vulnerabilities_by_ecosystem(extracted_dir, ecosystems=['npm', 'PyPI'], max_per_ecosystem=None):
    """Filter vulnerabilities for specified ecosystems and convert to DataFrame.
    
    Args:
        extracted_dir: Directory containing extracted JSON files
        ecosystems: List of ecosystems to filter for
        max_per_ecosystem: Dict mapping ecosystem to max count, or None for no limit
    """
    vulnerabilities = []
    extracted_path = Path(extracted_dir)
    
    # Track counts per ecosystem
    ecosystem_counts = {eco: 0 for eco in ecosystems}
    max_counts = max_per_ecosystem or {}
    
    # Find all JSON files in the extracted directory
    json_files = list(extracted_path.rglob('*.json'))
    print(f"Found {len(json_files)} JSON files")
    
    for json_file in json_files:
        # Check if we've reached limits for all ecosystems
        if max_per_ecosystem:
            if all(ecosystem_counts.get(eco, 0) >= max_counts.get(eco, float('inf')) 
                   for eco in ecosystems):
                print(f"Reached limits for all ecosystems. Stopping.")
                break
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                vuln_data = json.load(f)
            
            # Check if this vulnerability affects any of our target ecosystems
            affected = vuln_data.get('affected', [])
            for affected_item in affected:
                package = affected_item.get('package', {})
                ecosystem = package.get('ecosystem', '')
                
                if ecosystem in ecosystems:
                    # Check if we've reached the limit for this ecosystem
                    if max_per_ecosystem and ecosystem_counts[ecosystem] >= max_counts.get(ecosystem, float('inf')):
                        continue
                    
                    # Clean details field: replace newlines with spaces for better CSV viewing
                    details = vuln_data.get('details', '')
                    if details:
                        # Replace newlines and multiple spaces with single space
                        details = ' '.join(details.split())
                        # Truncate if too long (keep first 500 chars for CSV viewing)
                        if len(details) > 500:
                            details = details[:500] + '...'
                    
                    # Extract severity score if available
                    severity_data = vuln_data.get('severity', [])
                    severity_score = ''
                    severity_type = ''
                    if severity_data and len(severity_data) > 0:
                        first_severity = severity_data[0]
                        severity_type = first_severity.get('type', '')
                        if 'score' in first_severity:
                            severity_score = str(first_severity.get('score', ''))
                    
                    # Extract relevant information
                    vuln_record = {
                        'id': vuln_data.get('id', ''),
                        'ecosystem': ecosystem,
                        'package_name': package.get('name', ''),
                        'summary': vuln_data.get('summary', ''),
                        'details': details,  # Cleaned and truncated
                        'published': vuln_data.get('published', ''),
                        'modified': vuln_data.get('modified', ''),
                        'withdrawn': vuln_data.get('withdrawn', ''),
                        'severity_type': severity_type,
                        'severity_score': severity_score,
                        'severity_full': json.dumps(severity_data),  # Keep full JSON for reference
                        'database_specific': json.dumps(vuln_data.get('database_specific', {})),
                        'affected_ranges': json.dumps(affected_item.get('ranges', [])),
                        'versions': json.dumps(affected_item.get('versions', [])),
                    }
                    vulnerabilities.append(vuln_record)
                    ecosystem_counts[ecosystem] += 1
                    break  # Only add once per vulnerability, even if it affects multiple packages
        except (json.JSONDecodeError, KeyError, Exception) as e:
            print(f"Error processing {json_file}: {e}")
            continue
    
    print(f"Found {len(vulnerabilities)} vulnerabilities for ecosystems: {ecosystems}")
    print(f"Breakdown: {ecosystem_counts}")
    return pd.DataFrame(vulnerabilities)

def save_to_csv(df, output_file):
    """Save DataFrame to CSV file with proper escaping for multi-line fields."""
    print(f"Saving {len(df)} vulnerabilities to {output_file}...")
    # Use proper CSV escaping: quoting=1 (QUOTE_ALL) ensures all fields are quoted
    # This helps with fields containing commas, quotes, or newlines
    # lineterminator='\n' ensures consistent line endings
    df.to_csv(output_file, index=False, quoting=1, lineterminator='\n')
    print(f"Successfully saved to {output_file}")

def main():
    """Main function to download, filter, and save vulnerabilities."""
    # Create data directory if it doesn't exist
    data_dir = Path('data')
    data_dir.mkdir(exist_ok=True)
    
    # Create temporary directory for extraction
    with tempfile.TemporaryDirectory() as temp_dir:
        # Fetch and extract data from OSV
        extracted_dir = fetch_data_from_osv(temp_dir)
        
        # Filter for npm and PyPI ecosystems with limits
        max_per_ecosystem = {'npm': 1000, 'PyPI': 1000}
        df = filter_vulnerabilities_by_ecosystem(
            extracted_dir, 
            ecosystems=['npm', 'PyPI'],
            max_per_ecosystem=max_per_ecosystem
        )
        
        # Save to CSV in data folder
        output_file = data_dir / 'vulnerabilities_npm_pypi_lean.csv'
        save_to_csv(df, output_file)
        
        print(f"\nCompleted! Output file: {output_file}")
        print(f"Total vulnerabilities: {len(df)}")
        print(f"Breakdown by ecosystem:")
        print(df['ecosystem'].value_counts())

if __name__ == "__main__":
    main()
