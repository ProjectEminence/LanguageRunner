"""
Base class for language-specific test runners.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path


class BaseTestRunner(ABC):
    """Base class for language-specific test runners."""
    
    @abstractmethod
    def setup_environment(self, repo_path: str) -> Dict[str, Any]:
        """
        Setup the testing environment for the language.
        
        Args:
            repo_path: Path to the repository root
            
        Returns:
            Dictionary with setup results (success, output, error)
        """
        pass
    
    @abstractmethod
    def run_tests(self, repo_path: str, test_files: List[str], include_coverage: bool = False) -> Dict[str, Any]:
        """
        Run tests for the given test files.
        
        Args:
            repo_path: Path to the repository root
            test_files: List of test file paths (relative to repo_path)
            include_coverage: Whether to collect and return coverage data (default: False)
            
        Returns:
            Dictionary with test results:
            {
                "success": bool,
                "test_results": [
                    {
                        "test_file": str,
                        "test_name": str,
                        "status": "passed" | "failed",
                        "error": str (optional),
                        "output": str
                    }
                ],
                "coverage": {
                    "line_coverage": float,
                    "lines_covered": int,
                    "lines_total": int,
                    "files_covered": int,
                    "coverage_by_file": [...],
                    "generated_at": str
                } | None,
                "errors": List[str]
            }
        """
        pass

    @abstractmethod
    def run_tests_with_coverage(
        self,
        repo_path: str,
        test_files: List[str],
        coverage_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run tests with code coverage for the given test files.
        
        Args:
            repo_path: Path to the repository root
            test_files: List of test file paths (relative to repo_path)
            coverage_options: Optional dict with coverage configuration:
                - source: source directory to measure coverage (Python)
                - collect_coverage_from: paths to collect coverage from (TypeScript)
                - coverage_threshold: minimum coverage percentage required
        
        Returns:
            Dictionary with test results and coverage:
            {
                "success": bool,
                "test_results": [...],
                "coverage": {
                    "line_coverage": float,
                    "lines_covered": int,
                    "lines_total": int,
                    "files_covered": int,
                    "coverage_by_file": [...],
                    "generated_at": str
                } | None,
                "errors": List[str]
            }
        """
        pass
    
    @abstractmethod
    def detect_language(self, repo_path: str) -> bool:
        """
        Detect if this runner can handle the repository.
        
        Args:
            repo_path: Path to the repository root
            
        Returns:
            True if this runner can handle the repository
        """
        pass
