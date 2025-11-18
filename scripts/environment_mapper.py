"""
Environment Mapper
Detects the package ecosystem of a repository based on configuration files.
"""


"""
Supported Ecosystems:
    Python: pypi (requirements.txt, Pipfile, pyproject.toml, etc.)
    - JavaScript: npm (package.json, package-lock.json, yarn.lock, etc.)
    - Ruby: rubygems (Gemfile)
    - Java: maven, gradle (pom.xml, build.gradle)
    - .NET: nuget (.csproj, packages.config)
    - Go: go (go.mod)
    - Rust: cargo (Cargo.toml)
    - PHP: composer (composer.json)
    - Elixir: hex (mix.exs)
    - Dart: pub (pubspec.yaml)
    - Swift: swift (Package.swift)
"""
import os
from pathlib import Path
from typing import List, Optional, Dict


class EnvironmentMapper:
    """Maps repository files to their corresponding package ecosystems."""
    
    # Mapping of file patterns to ecosystems
    ECOSYSTEM_PATTERNS: Dict[str, List[str]] = {
        "pypi": [
            "requirements.txt",
            "Pipfile",
            "Pipfile.lock",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "poetry.lock",
        ],
        "npm": [
            "package.json",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "npm-shrinkwrap.json",
        ],
        "rubygems": [
            "Gemfile",
            "Gemfile.lock",
            "gems.rb",
            "gems.locked",
        ],
        "maven": [
            "pom.xml",
        ],
        "gradle": [
            "build.gradle",
            "build.gradle.kts",
            "settings.gradle",
            "settings.gradle.kts",
        ],
        "nuget": [
            "packages.config",
            "*.csproj",
            "*.vbproj",
            "*.fsproj",
            "paket.dependencies",
        ],
        "go": [
            "go.mod",
            "go.sum",
        ],
        "cargo": [
            "Cargo.toml",
            "Cargo.lock",
        ],
        "composer": [
            "composer.json",
            "composer.lock",
        ],
        "hex": [
            "mix.exs",
            "mix.lock",
        ],
        "pub": [
            "pubspec.yaml",
            "pubspec.lock",
        ],
        "swift": [
            "Package.swift",
            "Package.resolved",
        ],
    }
    
    def __init__(self, repository_path: str = "."):
        """
        Initialize the environment mapper.
        
        Args:
            repository_path: Path to the repository to scan
        """
        self.repository_path = Path(repository_path)
    
    def detect_ecosystems(self) -> List[str]:
        """
        Detect all package ecosystems present in the repository.
        
        Returns:
            List of detected ecosystem names (e.g., ["pypi", "npm"])
        """
        detected = []
        
        for ecosystem, patterns in self.ECOSYSTEM_PATTERNS.items():
            if self._has_any_file(patterns):
                detected.append(ecosystem)
        
        return detected
    
    def detect_primary_ecosystem(self) -> Optional[str]:
        """
        Detect the primary (most likely) package ecosystem.
        
        Returns:
            The primary ecosystem name, or None if no ecosystem detected
        """
        ecosystems = self.detect_ecosystems()
        
        if not ecosystems:
            return None
        
        # Return the first detected ecosystem
        # Could be made more sophisticated with scoring
        return ecosystems[0]
    
    def _has_any_file(self, patterns: List[str]) -> bool:
        """
        Check if any of the given file patterns exist in the repository.
        
        Args:
            patterns: List of file name patterns to check
            
        Returns:
            True if any pattern is found, False otherwise
        """
        for pattern in patterns:
            # Handle wildcard patterns
            if "*" in pattern:
                if list(self.repository_path.rglob(pattern)):
                    return True
            else:
                # Check in root directory
                if (self.repository_path / pattern).exists():
                    return True
                # Also check in common subdirectories
                for subdir in [".", "data", "src", "app"]:
                    if (self.repository_path / subdir / pattern).exists():
                        return True
        
        return False
    
    def get_ecosystem_info(self, ecosystem: str) -> Dict[str, str]:
        """
        Get detailed information about a specific ecosystem.
        
        Args:
            ecosystem: The ecosystem name
            
        Returns:
            Dictionary with ecosystem information
        """
        info_map = {
            "pypi": {
                "name": "PyPI",
                "full_name": "Python Package Index",
                "language": "Python",
                "url": "https://pypi.org",
            },
            "npm": {
                "name": "npm",
                "full_name": "Node Package Manager",
                "language": "JavaScript/Node.js",
                "url": "https://www.npmjs.com",
            },
            "rubygems": {
                "name": "RubyGems",
                "full_name": "RubyGems",
                "language": "Ruby",
                "url": "https://rubygems.org",
            },
            "maven": {
                "name": "Maven",
                "full_name": "Maven Central",
                "language": "Java",
                "url": "https://search.maven.org",
            },
            "gradle": {
                "name": "Gradle",
                "full_name": "Gradle",
                "language": "Java/Kotlin",
                "url": "https://gradle.org",
            },
            "nuget": {
                "name": "NuGet",
                "full_name": "NuGet Gallery",
                "language": ".NET",
                "url": "https://www.nuget.org",
            },
            "go": {
                "name": "Go",
                "full_name": "Go Modules",
                "language": "Go",
                "url": "https://pkg.go.dev",
            },
            "cargo": {
                "name": "Cargo",
                "full_name": "crates.io",
                "language": "Rust",
                "url": "https://crates.io",
            },
            "composer": {
                "name": "Composer",
                "full_name": "Packagist",
                "language": "PHP",
                "url": "https://packagist.org",
            },
            "hex": {
                "name": "Hex",
                "full_name": "Hex Package Manager",
                "language": "Elixir",
                "url": "https://hex.pm",
            },
            "pub": {
                "name": "Pub",
                "full_name": "Dart Pub",
                "language": "Dart",
                "url": "https://pub.dev",
            },
            "swift": {
                "name": "Swift",
                "full_name": "Swift Package Manager",
                "language": "Swift",
                "url": "https://swift.org/package-manager/",
            },
        }
        
        return info_map.get(ecosystem, {
            "name": ecosystem,
            "full_name": ecosystem,
            "language": "Unknown",
            "url": "",
        })


def detect_environment(repository_path: str = ".") -> Optional[str]:
    """
    Simple function to detect the primary ecosystem of a repository.
    
    Args:
        repository_path: Path to the repository to scan
        
    Returns:
        The ecosystem name (e.g., "pypi", "npm") or None
        
    Examples:
        >>> detect_environment(".")
        'pypi'
        
        >>> detect_environment("/path/to/node/project")
        'npm'
    """
    mapper = EnvironmentMapper(repository_path)
    return mapper.detect_primary_ecosystem()


def detect_all_environments(repository_path: str = ".") -> List[str]:
    """
    Detect all ecosystems present in a repository.
    
    Args:
        repository_path: Path to the repository to scan
        
    Returns:
        List of all detected ecosystem names
        
    Examples:
        >>> detect_all_environments(".")
        ['pypi', 'npm']
    """
    mapper = EnvironmentMapper(repository_path)
    return mapper.detect_ecosystems()


if __name__ == "__main__":
    # Example usage
    import sys
    
    repo_path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    mapper = EnvironmentMapper(repo_path)
    ecosystems = mapper.detect_ecosystems()
    
    if not ecosystems:
        print("WARNING: No recognized package ecosystems detected")
        sys.exit(1)
    
    print(f"Detected {len(ecosystems)} ecosystem(s):")
    for ecosystem in ecosystems:
        info = mapper.get_ecosystem_info(ecosystem)
        print(f"  - {ecosystem} ({info['full_name']} - {info['language']})")
    
    if len(ecosystems) > 1:
        print(f"\nPrimary ecosystem: {ecosystems[0]}")

