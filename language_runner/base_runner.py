"""
Base class for language-specific test runners.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List
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
    def run_tests(self, repo_path: str, test_files: List[str]) -> Dict[str, Any]:
        """
        Run tests for the given test files.
        
        Args:
            repo_path: Path to the repository root
            test_files: List of test file paths (relative to repo_path)
            
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
